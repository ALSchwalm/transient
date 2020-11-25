import beautifultable  # type: ignore
import json
import logging
import fcntl
import itertools
import os
import stat
import progressbar  # type: ignore
import re
import requests
import subprocess
import tarfile
import tempfile
import urllib.parse

from . import utils
from typing import cast, Optional, List, Dict, Any, Union, Tuple, IO, Pattern


_BLOCK_TRANSFER_SIZE = 64 * 1024  # 64KiB

# vm_name-disk_number-image_name-image_version
_VM_IMAGE_REGEX = re.compile(r"^[^\-]+-[^\-]+-[^\-]+$")

# image_name-image_version
_BACKEND_IMAGE_REGEX = re.compile(r"^[^\-]+$")


def storage_safe_encode(name: str) -> str:
    # Use URL quote so the names are still somewhat readable in the filesystem, but
    # we can unambiguously get the true name back for display purposes
    return urllib.parse.quote(name, safe="").replace("-", "%2D")


def storage_safe_decode(name: str) -> str:
    return urllib.parse.unquote(name)


class BaseImageProtocol:
    def __init__(self, regex: Pattern[str]) -> None:
        self.regex = regex

    def matches(self, candidate: str) -> bool:
        return self.regex.match(candidate) is not None

    def retrieve_image(
        self, store: "ImageStore", spec: "ImageSpec", destination: str
    ) -> None:
        # Do partial downloads into the working directory in the backend
        dest_name = os.path.basename(destination)
        temp_destination = os.path.join(store.working, dest_name)
        fd = self.__lock_backend_destination(temp_destination)

        # We now hold the lock. Either another process started the retrieval
        # and died (or never started at all) or they completed. If the final file exists,
        # the must have completed successfully so just return.
        if os.path.exists(destination):
            logging.info("Retrieval completed by another processes. Skipping.")
            os.close(fd)
            return None

        with os.fdopen(fd, "wb+") as temp_file:
            self._do_retrieve_image(store, spec, temp_file)

            # Now that the entire file is retrieved, atomically move it to the destination.
            # This avoids issues where a process was killed in the middle of retrieval
            os.rename(temp_destination, destination)

            # There is a qemu hotkey to commit a 'snapshot' to the backing file.
            # Making the backend images read-only prevents this.
            os.chmod(destination, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    def _do_retrieve_image(
        self, store: "ImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:
        raise RuntimeError("Protocol did not implement '_do_retrieve_image'")

    def __lock_backend_destination(self, dest: str) -> int:
        # By default, python 'open' call will truncate writable files. We can't allow that
        # as we don't yet hold the flock (and there is no way to open _and_ flock in one
        # call). So we use os.open to avoid the truncate.
        fd = os.open(dest, os.O_RDWR | os.O_CREAT)

        logging.debug(f"Attempting to acquire lock of '{dest}'")

        # This will block if another transient process is doing the retrieval. Once this
        # function returns, the lock is held until 'fd' is closed.
        try:
            # First attempt to acquire the lock non-blocking
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # OSError indicates the lock is held by someone else. Print a notice and then
            # block.
            logging.info(f"Retrieval of '{dest}' already in progress. Waiting.")
            fcntl.flock(fd, fcntl.LOCK_EX)

        logging.debug(f"Lock of '{dest}' acquired")

        return fd


class VagrantImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"vagrant", re.IGNORECASE))

    def __download_vagrant_info(self, image_name: str) -> Dict[str, Any]:
        url = f"https://app.vagrantup.com/api/v1/box/{image_name}"
        response = requests.get(url, allow_redirects=True)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise RuntimeError(
                f"Unable to download vagrant image '{image_name}' info. Maybe invalid image?"
            )
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
                assert isinstance(download_url, str)
                return download_url
        raise RuntimeError(
            "No version '{}' available for {} with provider libvirt".format(
                version, box_info["tag"]
            )
        )

    def _do_retrieve_image(
        self, store: "ImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:
        box_name, version = spec.source.split(":", 1)

        # For convenience, allow the user to specify the version with a v,
        # but that isn't how the API reports it
        if version.startswith("v"):
            version = version[1:]

        logging.info(f"Download vagrant image: box_name={box_name}, version={version}")

        box_info = self.__download_vagrant_info(box_name)
        logging.debug(f"Vagrant box info: {box_info}")

        box_url = self.__vagrant_box_url(version, box_info)

        print(f"Pulling from vagrant cloud: {box_name}:{version}")

        stream = requests.get(box_url, allow_redirects=True, stream=True)
        logging.debug(f"Response headers: {stream.headers}")

        stream.raise_for_status()
        total_length = progressbar.UnknownLength
        if "content-length" in stream.headers:
            total_length = int(stream.headers["content-length"])

        box_file = tempfile.TemporaryFile()

        # Do the actual download
        bar = utils.prepare_file_operation_bar(total_length)
        for idx, block in enumerate(stream.iter_content(_BLOCK_TRANSFER_SIZE)):
            box_file.write(block)
            bar.update(idx * _BLOCK_TRANSFER_SIZE)
        bar.finish()
        box_file.flush()
        box_file.seek(0)

        print("Download completed. Starting image extraction.")

        # libvirt boxes _should_ just be tar.gz files with a box.img file, but some
        # images put these in subdirectories. Try to detect that.
        with tarfile.open(fileobj=box_file, mode="r") as tar:
            image_info = [
                info for info in tar.getmembers() if info.name.endswith("box.img")
            ][0]
            in_stream = tar.extractfile(image_info.name)
            assert in_stream is not None

            utils.copy_with_progress(in_stream, destination, image_info.size)

        logging.info("Image extraction completed.")


class FrontendImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"frontend", re.IGNORECASE))

    def _do_retrieve_image(
        self, store: "ImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:
        vm_name, source = spec.source.split("@", 1)

        print(f"Copying image '{source}' for VM '{vm_name}' as new backend '{spec.name}'")

        candidates = store.frontend_image_list(vm_name, source)
        if len(candidates) == 0:
            raise RuntimeError(f"No backend image '{source}' for VM '{vm_name}'")
        elif len(candidates) > 1:
            # This should be impossible, but check anyway
            raise RuntimeError(f"Ambiguous backend image '{source}' for VM '{vm_name}'")
        frontend_image = candidates[0]
        with open(frontend_image.path, "rb") as existing_file:
            utils.copy_with_progress(
                existing_file, destination, frontend_image.actual_size
            )

        logging.info("Image copy complete.")


class FileImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"file", re.IGNORECASE))

    def _do_retrieve_image(
        self, store: "ImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:

        print(f"Copying '{spec.source}' as new backend '{spec.name}'")

        with open(spec.source, "rb") as existing_file:
            size = existing_file.seek(0, os.SEEK_END)
            existing_file.seek(0)
            utils.copy_with_progress(existing_file, destination, size)

        logging.info("File copy complete.")


class HttpImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"http", re.IGNORECASE))

    def _do_retrieve_image(
        self, store: "ImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:

        print(f"Downloading image from '{spec.source}'")

        stream = requests.get(spec.source, allow_redirects=True, stream=True)
        logging.debug(f"Response headers: {stream.headers}")

        stream.raise_for_status()
        total_length = progressbar.UnknownLength
        if "content-length" in stream.headers:
            total_length = int(stream.headers["content-length"])

        bar = utils.prepare_file_operation_bar(total_length)
        for idx, block in enumerate(stream.iter_content(_BLOCK_TRANSFER_SIZE)):
            destination.write(block)
            bar.update(idx * _BLOCK_TRANSFER_SIZE)
        bar.finish()

        logging.info("Download complete.")


_IMAGE_SPEC = re.compile(r"^([^,]+?)(?:,(.+?)=(.+))?$")
_IMAGE_PROTOCOLS = [
    VagrantImageProtocol(),
    FrontendImageProtocol(),
    HttpImageProtocol(),
    FileImageProtocol(),
]


class ImageSpec:
    name: str
    source_proto: BaseImageProtocol
    source: str

    def __init__(self, spec: str) -> None:
        parsed = _IMAGE_SPEC.match(spec)
        if parsed is None:
            raise RuntimeError(f"Invalid image spec '{spec}'")
        self.name, proto, self.source = parsed.groups()

        # If no protocol is specified, use vagrant
        if proto is None:
            self.source_proto = VagrantImageProtocol()
            self.source = self.name
            return

        for protocol in _IMAGE_PROTOCOLS:
            if protocol.matches(proto):
                self.source_proto = protocol
                return
        raise RuntimeError(f"Unknown image source protocol '{proto}'")


class BaseImageInfo:
    store: "ImageStore"
    virtual_size: int
    actual_size: int
    filename: str
    format: str
    path: str
    image_info: Dict[str, Any]

    def __init__(self, store: "ImageStore", path: str) -> None:
        stdout, _ = utils.run_check_retcode(
            [store.qemu_img_bin, "info", "-U", "--output=json", path]
        )
        assert stdout is not None
        self.image_info = json.loads(stdout)
        self.store = store
        self.virtual_size = self.image_info["virtual-size"]
        self.actual_size = self.image_info["actual-size"]
        self.filename = os.path.split(self.image_info["filename"])[-1]
        self.format = self.image_info["format"]
        self.path = path


class BackendImageInfo(BaseImageInfo):
    identifier: str

    def __init__(self, store: "ImageStore", path: str) -> None:
        super().__init__(store, path)
        self.identifier = storage_safe_decode(self.filename)


class FrontendImageInfo(BaseImageInfo):
    vm_name: str
    disk_number: int
    backend: Optional[BackendImageInfo]

    def __init__(self, store: "ImageStore", path: str):
        super().__init__(store, path)
        vm_name, number, image = self.filename.split("-")
        self.vm_name = storage_safe_decode(vm_name)
        self.disk_number = int(number)
        backend_path = self.image_info["full-backing-filename"]
        try:
            self.backend = BackendImageInfo(store, backend_path)
        except utils.TransientProcessError:
            # If the path doesn't exist, it was either deleted before
            # we could run qemu-img, or it never existed at all
            if not os.path.exists(backend_path):
                self.backend = None
            else:
                raise


def format_frontend_image_table(
    list: List[FrontendImageInfo],
) -> beautifultable.BeautifulTable:
    table = beautifultable.BeautifulTable()
    table.column_headers = [
        "VM Name",
        "Backend Image",
        "Disk Num",
        "Real Size",
        "Virt Size",
    ]
    table.set_style(beautifultable.BeautifulTable.STYLE_BOX)
    table.column_alignments["VM Name"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["Backend Image"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["Disk Num"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments["Real Size"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments["Virt Size"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    for image in list:
        if image.backend is None:
            backend_identifier = "--NOT FOUND--"
        else:
            backend_identifier = image.backend.identifier
        table.append_row(
            [
                image.vm_name,
                backend_identifier,
                image.disk_number,
                utils.format_bytes(image.actual_size),
                utils.format_bytes(image.virtual_size),
            ]
        )
    return table


def format_backend_image_table(
    list: List[BackendImageInfo],
) -> beautifultable.BeautifulTable:
    table = beautifultable.BeautifulTable()
    table.column_headers = ["Image Name", "Real Size", "Virt Size"]
    table.set_style(beautifultable.BeautifulTable.STYLE_BOX)
    table.column_alignments["Image Name"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["Real Size"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments["Virt Size"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    for image in list:
        table.append_row(
            [
                image.identifier,
                utils.format_bytes(image.actual_size),
                utils.format_bytes(image.virtual_size),
            ]
        )
    return table


def format_image_table(
    list: List[BaseImageInfo],
) -> Tuple[beautifultable.BeautifulTable, beautifultable.BeautifulTable]:
    frontend = [img for img in list if isinstance(img, FrontendImageInfo)]
    backend = [img for img in list if isinstance(img, BackendImageInfo)]
    return (format_frontend_image_table(frontend), format_backend_image_table(backend))


class ImageStore:
    backend: str
    frontend: str
    working: str
    qemu_img_bin: str

    def __init__(
        self, *, backend_dir: Optional[str] = None, frontend_dir: Optional[str] = None
    ) -> None:

        self.backend = os.path.abspath(backend_dir or self.__default_backend_dir())
        self.frontend = os.path.abspath(frontend_dir or self.__default_frontend_dir())
        self.working = self.__working_dir()
        self.qemu_img_bin = self.__default_qemu_img_bin()

        if not os.path.exists(self.backend):
            logging.debug(f"Creating missing ImageStore backend at '{self.backend}'")
            os.makedirs(self.backend, exist_ok=True)

        if not os.path.exists(self.frontend):
            logging.debug(f"Creating missing ImageStore frontend at '{self.frontend}'")
            os.makedirs(self.frontend, exist_ok=True)

        if not os.path.exists(self.working):
            os.makedirs(self.working, exist_ok=True)

    def __working_dir(self) -> str:
        # Note that the working directory must be in the same filesystem as
        # the backend, to allow atomic movement of files.
        return os.path.join(self.backend, ".working")

    def __default_backend_dir(self) -> str:
        env_specified = os.getenv("TRANSIENT_BACKEND")
        if env_specified is not None:
            return env_specified
        home = utils.transient_data_home()
        return os.path.join(home, "backend")

    def __default_frontend_dir(self) -> str:
        env_specified = os.getenv("TRANSIENT_FRONTEND")
        if env_specified is not None:
            return env_specified
        home = utils.transient_data_home()
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
            raise RuntimeError(f"Invalid image file name: '{filename}'")

    def backend_path(self, spec: ImageSpec) -> str:
        safe_name = storage_safe_encode(spec.name)
        return os.path.join(self.backend, safe_name)

    def retrieve_image(self, image_spec: str) -> BackendImageInfo:
        spec = ImageSpec(image_spec)
        destination = self.backend_path(spec)

        if os.path.exists(destination):
            logging.info(f"Image '{spec.name}' already exists. Skipping retrieval")
            return BackendImageInfo(self, destination)

        print(f"Unable to find image '{spec.name}' in backend")

        spec.source_proto.retrieve_image(self, spec, destination)

        logging.info(f"Finished retrieving image: {spec.name}")
        return BackendImageInfo(self, destination)

    def create_vm_image(
        self, image_spec: str, vm_name: str, num: int
    ) -> FrontendImageInfo:
        backing_image = self.retrieve_image(image_spec)
        safe_vmname = storage_safe_encode(vm_name)
        safe_image_identifier = storage_safe_encode(backing_image.identifier)
        new_image_path = os.path.join(
            self.frontend, f"{safe_vmname}-{num}-{safe_image_identifier}"
        )

        if os.path.exists(new_image_path):
            logging.info(f"VM image '{new_image_path}' already exists. Skipping create.")
            return FrontendImageInfo(self, new_image_path)

        logging.info(
            f"Creating VM Image '{new_image_path}' from backing image '{backing_image.path}'"
        )

        utils.run_check_retcode(
            [
                self.qemu_img_bin,
                "create",
                "-f",
                "qcow2",
                "-o",
                f"backing_file={backing_image.path}",
                new_image_path,
            ]
        )

        logging.info(f"VM Image '{new_image_path}' created")
        return FrontendImageInfo(self, new_image_path)

    def frontend_image_list(
        self, vm_name: Optional[str] = None, image_identifier: Optional[str] = None
    ) -> List[FrontendImageInfo]:
        images = []
        for candidate in os.listdir(self.frontend):
            path = os.path.join(self.frontend, candidate)
            if not os.path.isfile(path) or not _VM_IMAGE_REGEX.match(candidate):
                continue
            try:
                image_info = FrontendImageInfo(self, path)
            except utils.TransientProcessError:
                # If the path doesn't exist anymore, then we raced with something
                # that deleted the file, so just continue
                if not os.path.exists(path):
                    continue
                else:
                    raise
            if vm_name is not None:
                if image_info.vm_name != vm_name:
                    continue
            if image_identifier is not None:
                if (
                    image_info.backend is not None
                    and image_info.backend.identifier != image_identifier
                ):
                    continue
            images.append(image_info)
        return images

    def backend_image_list(
        self, image_identifier: Optional[str] = None
    ) -> List[BackendImageInfo]:
        images = []
        for candidate in os.listdir(self.backend):
            path = os.path.join(self.backend, candidate)
            if not os.path.isfile(path) or not _BACKEND_IMAGE_REGEX.match(candidate):
                continue
            try:
                image_info = BackendImageInfo(self, path)
            except utils.TransientProcessError:
                if not os.path.exists(path):
                    continue
                else:
                    raise
            if image_identifier is not None:
                if image_info.identifier != image_identifier:
                    continue
            images.append(image_info)
        return images

    def delete_image(self, image: BaseImageInfo) -> None:
        os.remove(image.path)
