import beautifultable  # type: ignore
import json
import logging
import fcntl
import itertools
import os
import progressbar  # type: ignore
import re
import requests
import subprocess
import tarfile
import urllib.parse

from . import utils
from typing import cast, Optional, List, Dict, Any, Union, Tuple


_FALLBACK_DATA_PATH = "/tmp"
_BLOCK_TRANSFER_SIZE = 64 * 1024  # 64KiB

# vm_name-disk_number-image_name-image_version
_VM_IMAGE_REGEX = re.compile(r"^[^\-]+-[^\-]+-[^\-]+$")

# image_name-image_version
_BACKEND_IMAGE_REGEX = re.compile(r"^[^\-]+$")


def _storage_safe_encode(name: str) -> str:
    # Use URL quote so the names are still somewhat readable in the filesystem, but
    # we can unambiguously get the true name back for display purposes
    return urllib.parse.quote(name, safe="").replace("-", "%2D")


def _storage_safe_decode(name: str) -> str:
    return urllib.parse.unquote(name)


class BaseImageInfo:
    store: 'ImageStore'
    virtual_size: int
    actual_size: int
    filename: str
    format: str
    path: str
    image_info: Dict[str, Any]

    def __init__(self, store: 'ImageStore', path: str):
        stdout = subprocess.check_output([store.qemu_img_bin,
                                          "info", "-U", "--output=json", path])
        self.image_info = json.loads(stdout)
        self.store = store
        self.virtual_size = self.image_info["virtual-size"]
        self.actual_size = self.image_info["actual-size"]
        self.filename = os.path.split(self.image_info["filename"])[-1]
        self.format = self.image_info["format"]
        self.path = path


class BackendImageInfo(BaseImageInfo):
    identifier: str

    def __init__(self, store: 'ImageStore', path: str):
        super().__init__(store, path)
        self.identifier = _storage_safe_decode(self.filename)


class FrontendImageInfo(BaseImageInfo):
    vm_name: str
    disk_number: int
    backend: BackendImageInfo

    def __init__(self, store: 'ImageStore', path: str):
        super().__init__(store, path)
        vm_name, number, image = self.filename.split("-")
        self.vm_name = _storage_safe_decode(vm_name)
        self.disk_number = int(number)
        self.backend = BackendImageInfo(store, self.image_info["full-backing-filename"])


def format_frontend_image_table(list: List[FrontendImageInfo]) -> beautifultable.BeautifulTable:
    table = beautifultable.BeautifulTable()
    table.column_headers = ["VM Name", "Backend Image", "Disk Num", "Real Size", "Virt Size"]
    table.set_style(beautifultable.BeautifulTable.STYLE_BOX)
    table.column_alignments['VM Name'] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments['Backend Image'] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments['Disk Num'] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments['Real Size'] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments['Virt Size'] = beautifultable.BeautifulTable.ALIGN_RIGHT
    for image in list:
        table.append_row([image.vm_name, image.backend.identifier,
                          image.disk_number, utils.format_bytes(image.actual_size),
                          utils.format_bytes(image.virtual_size)])
    return table


def format_backend_image_table(list: List[BackendImageInfo]) -> beautifultable.BeautifulTable:
    table = beautifultable.BeautifulTable()
    table.column_headers = ["Image Name", "Real Size", "Virt Size"]
    table.set_style(beautifultable.BeautifulTable.STYLE_BOX)
    table.column_alignments['Image Name'] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments['Real Size'] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments['Virt Size'] = beautifultable.BeautifulTable.ALIGN_RIGHT
    for image in list:
        table.append_row([image.identifier, utils.format_bytes(image.actual_size),
                          utils.format_bytes(image.virtual_size)])
    return table


def format_image_table(list: List[BaseImageInfo]) -> Tuple[beautifultable.BeautifulTable,
                                                           beautifultable.BeautifulTable]:
    frontend = [img for img in list if isinstance(img, FrontendImageInfo)]
    backend = [img for img in list if isinstance(img, BackendImageInfo)]
    return (format_frontend_image_table(frontend),
            format_backend_image_table(backend))


class ImageStore:
    backend: str
    frontend: str
    qemu_img_bin: str

    def __init__(self, *, backend_dir: Optional[str] = None,
                 frontend_dir: Optional[str] = None) -> None:

        self.backend = backend_dir or self.__default_backend_dir()
        self.frontend = frontend_dir or self.__default_frontend_dir()
        self.qemu_img_bin = self.__default_qemu_img_bin()

        if not os.path.exists(self.backend):
            logging.debug("Creating missing ImageStore backend at '{}'".format(self.backend))
            os.makedirs(self.backend, exist_ok=True)

        if not os.path.exists(self.frontend):
            logging.debug("Creating missing ImageStore frontend at '{}'".format(self.frontend))
            os.makedirs(self.frontend, exist_ok=True)

    def __prepare_file_operation_bar(self, filesize):
        return progressbar.ProgressBar(
            maxval=filesize,
            widgets=[
                progressbar.Percentage(),
                ' ',
                progressbar.Bar(),
                ' ',
                progressbar.FileTransferSpeed(),
                ' | ',
                progressbar.DataSize(),
                ' | ',
                progressbar.ETA(),
            ])

    def __transient_data_home(self) -> str:
        user_home = os.getenv("HOME")
        default_xdg_data_home = None
        if user_home is not None:
            default_xdg_data_home = os.path.join(user_home, ".local", "share")

        xdg_data_home = os.getenv("XDG_DATA_HOME", default_xdg_data_home)
        if xdg_data_home is None:
            logging.warning("$HOME and $XDG_DATA_HOME not set. Using {}"
                            .format(_FALLBACK_DATA_PATH))
            xdg_data_home = _FALLBACK_DATA_PATH
        return os.path.join(xdg_data_home, "transient")

    def __default_backend_dir(self) -> str:
        env_specified = os.getenv("TRANSIENT_BACKEND")
        if env_specified is not None:
            return env_specified
        home = self.__transient_data_home()
        return os.path.join(home, "backend")

    def __default_frontend_dir(self) -> str:
        env_specified = os.getenv("TRANSIENT_FRONTEND")
        if env_specified is not None:
            return env_specified
        home = self.__transient_data_home()
        return os.path.join(home, "frontend")

    def __default_qemu_img_bin(self) -> str:
        return "qemu-img"

    def __image_info(self, path: str) -> BaseImageInfo:
        filename = os.path.split(path)[-1]
        if _VM_IMAGE_REGEX.match(filename):
            return FrontendImageInfo(self, path)
        elif _BACKEND_IMAGE_REGEX.match(filename):
            return BackendImageInfo(self, path)
        else:
            raise RuntimeError("Invalid image file name: '{}'".format(filename))

    def __download_vagrant_info(self, image_name: str) -> Dict[str, Any]:
        url = "https://app.vagrantup.com/api/v1/box/{}".format(image_name)
        response = requests.get(url, allow_redirects=True)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise RuntimeError("Unable to download vagrant image '{}' info. Maybe invalid image?"
                               .format(image_name))
        return cast(Dict[str, Any], json.loads(response.content))

    def __vagrant_box_url(self, version: str, box_info: Dict[str, Any]) -> str:
        for version_info in box_info["versions"]:
            if version_info["version"] != version:
                continue
            for provider in version_info["providers"]:
                # TODO: we should also support 'qemu'
                if provider["name"] != "libvirt":
                    continue

                download_url = provider["download_url"]
                assert(isinstance(download_url, str))
                return download_url
        raise RuntimeError("No version '{}' available for {} with provider libvirt"
                           .format(version, box_info["tag"]))

    def __download_vagrant_image(self, image_identifier: str, destination: str) -> None:
        box_name, version = image_identifier.split(":")

        # For convenience, allow the user to specify the version with a v,
        # but that isn't how the API reports it
        if version.startswith("v"):
            version = version[1:]

        logging.info("Download vagrant image: box_name={}, version={}".format(
            box_name, version))

        box_info = self.__download_vagrant_info(box_name)
        logging.debug("Vagrant box info: {}".format(box_info))

        box_url = self.__vagrant_box_url(version, box_info)

        print("Pulling from vagranthub: {}:{}".format(box_name, version))

        box_destination = destination + ".box"

        # By default, python 'open' call will truncate writable files. We can't allow that
        # as we don't yet hold the flock (and there is no way to open _and_ flock in one
        # call). So we use os.open to avoid the truncate.
        box_fd = os.open(box_destination, os.O_RDWR | os.O_CREAT)

        logging.debug("Attempting to acquire lock of '{}'".format(box_destination))

        # This will block if another transient process is doing the download. The lock must
        # be held until after the point where we atomically rename the extracted item to
        # its final name.
        try:
            # First attempt to acquire the lock non-blocking
            fcntl.flock(box_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # OSError indicates the lock is held by someone else. Print a notice and then
            # block.
            logging.info("Download in progress from another process. Waiting.")
            fcntl.flock(box_fd, fcntl.LOCK_EX)

        logging.debug("Lock of '{}' now held".format(box_destination))

        # We now hold the lock. Either another process started the download/extraction
        # and died (or never started at all) or they completed. If the final file exists,
        # the must have completed successfully so just return.
        if os.path.exists(destination):
            logging.info("Download completed by another processes. Skipping.")
            os.close(box_fd)
            return

        stream = requests.get(box_url, allow_redirects=True, stream=True)
        logging.debug("Response headers: {}".format(stream.headers))

        stream.raise_for_status()
        total_length = progressbar.UnknownLength
        if "content-length" in stream.headers:
            total_length = int(stream.headers["content-length"])

        # Convenience wrapper around the fd
        box_file = os.fdopen(box_fd, 'wb+')

        # Do the actual download
        bar = self.__prepare_file_operation_bar(total_length)
        for idx, block in enumerate(stream.iter_content(_BLOCK_TRANSFER_SIZE)):
            box_file.write(block)
            bar.update(idx * _BLOCK_TRANSFER_SIZE)
        bar.finish()
        box_file.flush()
        box_file.seek(0)

        print("Download completed. Starting image extraction.")

        # libvirt boxes _should_ just be tar.gz files with a box.img file, but some
        # images put these in subdirectories. Try to detect that.
        part_destination = destination + ".part"
        with tarfile.open(fileobj=box_file, mode="r") as tar:
            image_info = [info for info in tar.getmembers()
                          if info.name.endswith("box.img")][0]
            in_stream = tar.extractfile(image_info.name)
            assert(in_stream is not None)

            out_stream = open(part_destination, 'wb')

            bar = self.__prepare_file_operation_bar(image_info.size)
            for idx in itertools.count():
                block = in_stream.read(_BLOCK_TRANSFER_SIZE)
                if not block:
                    break
                out_stream.write(block)
                bar.update(idx * _BLOCK_TRANSFER_SIZE)
            bar.finish()

        logging.info("Image extraction completed.")

        # Now that the entire file is extracted, atomically move it to the destination.
        # This avoids issues where a process was killed in the middle of extracting.
        os.rename(part_destination, destination)

        # And clean up the box
        os.remove(box_destination)
        box_file.close()

    def retrieve_image(self, image_identifier: str) -> BackendImageInfo:
        safe_name = _storage_safe_encode(image_identifier)
        destination = os.path.join(self.backend, safe_name)

        if os.path.exists(destination):
            logging.info("Image '{}' already exists. Skipping download".format(
                image_identifier))
            return BackendImageInfo(self, destination)

        print("Unable to find image '{}' in backend".format(image_identifier))

        # For now, we only support vagrant images
        self.__download_vagrant_image(image_identifier, destination)

        logging.info("Finished downloading image: {}".format(image_identifier))
        return BackendImageInfo(self, destination)

    def create_vm_image(self, image_name: str, vm_name: str, num: int) -> FrontendImageInfo:
        backing_image = self.retrieve_image(image_name)
        safe_vmname = _storage_safe_encode(vm_name)
        safe_image_identifier = _storage_safe_encode(backing_image.identifier)
        new_image_path = os.path.join(
            self.frontend, "{}-{}-{}".format(safe_vmname, num, safe_image_identifier))

        if os.path.exists(new_image_path):
            logging.info("VM image '{}' already exists. Skipping create.".format(new_image_path))
            return FrontendImageInfo(self, new_image_path)

        logging.info("Creating VM Image '{}' from backing image '{}'".format(
            new_image_path, backing_image.path))

        subprocess.check_output([self.qemu_img_bin,
                                 "create", "-f", "qcow2",
                                 "-o", "backing_file={}".format(backing_image.path),
                                 new_image_path])

        logging.info("VM Image '{}' created".format(new_image_path))
        return FrontendImageInfo(self, new_image_path)

    def frontend_image_list(self, vm_name: Optional[str] = None,
                            image_identifier: Optional[str] = None) -> List[FrontendImageInfo]:
        images = []
        for candidate in os.listdir(self.frontend):
            if not _VM_IMAGE_REGEX.match(candidate):
                continue
            path = os.path.join(self.frontend, candidate)
            image_info = FrontendImageInfo(self, path)
            if vm_name is not None:
                if image_info.vm_name != vm_name:
                    continue
            if image_identifier is not None:
                if image_info.backend.identifier != image_identifier:
                    continue
            images.append(image_info)
        return images

    def backend_image_list(self, image_identifier: Optional[str] = None) -> List[BackendImageInfo]:
        images = []
        for candidate in os.listdir(self.backend):
            if not _BACKEND_IMAGE_REGEX.match(candidate):
                continue
            path = os.path.join(self.backend, candidate)
            image_info = BackendImageInfo(self, path)
            if image_identifier is not None:
                if image_info.identifier != image_identifier:
                    continue
            images.append(image_info)
        return images

    def delete_image(self, image: BaseImageInfo) -> None:
        os.remove(image.path)
