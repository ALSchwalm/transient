import collections
import contextlib
import json
import logging
import fcntl
import os
import progressbar  # type: ignore
import re
import requests
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import toml
import urllib.parse
import uuid

from . import configuration
from . import utils
from typing import (
    cast,
    Optional,
    List,
    Dict,
    Any,
    Union,
    Tuple,
    IO,
    Pattern,
    Iterator,
    TextIO,
)

# Time to wait in seconds between attempts to acquire vmstate lock
_VMSTATE_LOCK_INTERVAL = 0.1

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
        self, store: "BackendImageStore", spec: "ImageSpec", destination: str
    ) -> None:
        # Do partial downloads into the working directory in the backend
        dest_name = os.path.basename(destination)
        temp_destination = os.path.join(store.working, dest_name)

        with utils.lock_file(temp_destination, "wb+") as temp_file:
            # We now hold the lock. Either another process started the retrieval
            # and died (or never started at all) or they completed. If the final file exists,
            # the must have completed successfully so just return.
            if os.path.exists(destination):
                logging.info("Retrieval completed by another processes. Skipping.")
                return None

            self._do_retrieve_image(store, spec, temp_file)

            # Now that the entire file is retrieved, atomically move it to the destination.
            # This avoids issues where a process was killed in the middle of retrieval
            os.rename(temp_destination, destination)

            # There is a qemu hotkey to commit a 'snapshot' to the backing file.
            # Making the backend images read-only prevents this.
            utils.make_path_readonly(destination)

    def _do_retrieve_image(
        self, store: "BackendImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:
        raise RuntimeError("Protocol did not implement '_do_retrieve_image'")


class VagrantImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"vagrant", re.IGNORECASE))

    def __download_vagrant_info(self, image_name: str) -> Dict[str, Any]:
        url = f"https://app.vagrantup.com/api/v1/box/{image_name}"
        response = requests.get(url, allow_redirects=True)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise utils.TransientError(
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
        raise utils.TransientError(
            "No version '{}' available for {} with provider libvirt".format(
                version, box_info["tag"]
            )
        )

    def _do_retrieve_image(
        self, store: "BackendImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:
        try:
            box_name, version = spec.source.split(":", 1)
        except ValueError:
            raise utils.TransientError(
                f"No image named {spec.source} found in the backend, and no "
                "version provided, so it cannot be downloaded."
            )

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


class FileImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"file", re.IGNORECASE))

    def _do_retrieve_image(
        self, store: "BackendImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:

        print(f"Copying '{spec.source}' as new backend '{spec.name}'")

        with open(spec.source, "rb") as existing_file:
            size = existing_file.seek(0, os.SEEK_END)
            existing_file.seek(0)
            utils.copy_with_progress(existing_file, destination, size, decompress=True)

        logging.info("File copy complete.")


class HttpImageProtocol(BaseImageProtocol):
    def __init__(self) -> None:
        super().__init__(re.compile(r"http", re.IGNORECASE))

    def _do_retrieve_image(
        self, store: "BackendImageStore", spec: "ImageSpec", destination: IO[bytes]
    ) -> None:

        print(f"Downloading image from '{spec.source}'")

        stream = requests.get(spec.source, allow_redirects=True, stream=True)
        logging.debug(f"Response headers: {stream.headers}")

        stream.raise_for_status()
        total_length = progressbar.UnknownLength
        if "content-length" in stream.headers:
            total_length = int(stream.headers["content-length"])

        bar = utils.prepare_file_operation_bar(total_length)
        decompressor = utils.StreamDecompressor()
        for idx, block in enumerate(stream.iter_content(_BLOCK_TRANSFER_SIZE)):
            destination.write(decompressor.decompress(block))
            bar.update(idx * _BLOCK_TRANSFER_SIZE)
        bar.finish()

        logging.info("Download complete.")


_IMAGE_SPEC = re.compile(r"^([^,]+?)(?:,(.+?)=(.+))?$")
_IMAGE_PROTOCOLS = [
    VagrantImageProtocol(),
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
            raise utils.TransientError(f"Invalid image spec '{spec}'")
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
        raise utils.TransientError(f"Unknown image source protocol '{proto}'")


class BaseImageInfo:
    store: "BackendImageStore"
    virtual_size: int
    actual_size: int
    filename: str
    format: str
    path: str
    image_info: Dict[str, Any]

    def __init__(self, store: "BackendImageStore", path: str) -> None:
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

    def __init__(self, store: "BackendImageStore", path: str) -> None:
        super().__init__(store, path)
        self.identifier = storage_safe_decode(self.filename)


class FrontendImageInfo(BaseImageInfo):
    vm_name: str
    disk_number: int
    backend: Optional[BackendImageInfo]

    def __init__(self, store: "BackendImageStore", path: str):
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


class BackendImageStore:
    backend: str
    working: str
    qemu_img_bin: str

    def __init__(self, *, path: Optional[str] = None) -> None:

        self.backend = os.path.abspath(path or utils.default_backend_dir())
        self.working = self.__working_dir()
        self.qemu_img_bin = self.__default_qemu_img_bin()

        if not os.path.exists(self.backend):
            logging.debug(
                f"Creating missing BackendImageStore backend at '{self.backend}'"
            )
            os.makedirs(self.backend, exist_ok=True)

        if not os.path.exists(self.working):
            os.makedirs(self.working, exist_ok=True)

    def __working_dir(self) -> str:
        # Note that the working directory must be in the same filesystem as
        # the backend, to allow atomic movement of files.
        return os.path.join(self.backend, ".working")

    def __default_qemu_img_bin(self) -> str:
        return "qemu-img"

    def __image_info(self, path: str) -> BaseImageInfo:
        filename = os.path.split(path)[-1]
        if _VM_IMAGE_REGEX.match(filename):
            return FrontendImageInfo(self, path)
        elif _BACKEND_IMAGE_REGEX.match(filename):
            return BackendImageInfo(self, path)
        else:
            raise utils.TransientError(f"Invalid image file name: '{filename}'")

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

    def commit_vmstate(self, state: "VmPersistentState", name: str) -> BackendImageInfo:
        # FIXME: the first image is not necessarily the primary image
        primary_image = state.images[0]

        safe_name = storage_safe_encode(name)

        destination = os.path.join(self.backend, safe_name)
        working = os.path.join(self.working, safe_name)

        with utils.lock_file(working, "wb") as _:
            if os.path.exists(destination):
                raise utils.TransientError(
                    msg=f"An image with the name '{name}' already exists"
                )

            print(f"Converting vm image to new backend image '{name}'")

            # Use 'convert' to flatten the image, so we don't have
            # arbitrarily long qcow backing chains
            utils.run_check_retcode(
                [
                    self.qemu_img_bin,
                    "convert",
                    primary_image.path,
                    "-O" "qcow2",
                    "-p",
                    working,
                ],
                capture_stdout=False,
                capture_stderr=False,
            )

            utils.make_path_readonly(working)
            os.rename(working, destination)

        return BackendImageInfo(self, destination)

    def contains_image(self, name: str) -> bool:
        safe_name = storage_safe_encode(name)
        return os.path.exists(os.path.join(self.backend, safe_name))


class VmPersistentState:
    name: str
    images: List[FrontendImageInfo]
    config: configuration.CreateConfig
    store: "VmStore"

    def __init__(
        self,
        name: str,
        images: List[FrontendImageInfo],
        config: configuration.CreateConfig,
        vmstore: "VmStore",
    ):
        self.name = name
        self.images = images
        self.config = config
        self.store = vmstore


class VmStore:
    backend: BackendImageStore
    path: str

    def __init__(self, *, backend: BackendImageStore, path: Optional[str] = None) -> None:
        self.backend = backend
        self.path = path if path is not None else utils.default_vmstore_dir()

        if not os.path.exists(self.path):
            logging.debug(f"Creating missing VmStore backend at '{self.path}'")
            os.makedirs(self.path, exist_ok=True)

    def __vm_dir(self, name: str) -> str:
        return os.path.join(self.path, name)

    def create_vmstate(self, config: configuration.CreateConfig) -> str:
        # TODO: this should be made in a tmpdir and moved once finished
        if config.name is None:
            name = str(uuid.uuid4())
        else:
            name = config.name

        vmdir = self.__vm_dir(name)

        if os.path.exists(vmdir):
            raise utils.TransientError(f"A VM with name {name} already exists")

        logging.debug(f"Creating vmdir at {vmdir}")
        os.mkdir(vmdir)

        logging.info(f"Creating vm images for vm name={name}")
        images = [self.__create_vm_image(config.primary_image, name, 0)]

        self.__create_vm_config(name, config)

        return name

    def unsafe_rm_vmstate_by_name(self, name: str) -> None:
        shutil.rmtree(self.__vm_dir(name))

    def rm_vmstate(self, state: VmPersistentState) -> None:
        shutil.rmtree(self.__vm_dir(state.name))

    def rm_vmstate_by_name(self, name: str, lock_timeout: Optional[float] = None) -> None:
        with self.lock_vmstate_by_name(name, timeout=lock_timeout) as _state:
            shutil.rmtree(self.__vm_dir(name))

    def __create_vm_config(
        self, vm_name: str, config: configuration.CreateConfig
    ) -> None:
        with open(os.path.join(self.__vm_dir(vm_name), "config"), "w") as f:
            # Always keep the keys in order when we dump them
            f.write(toml.dumps(collections.OrderedDict(sorted(config.items()))))

    def __create_vm_image(
        self, image_spec: str, vm_name: str, num: int
    ) -> FrontendImageInfo:
        backing_image = self.backend.retrieve_image(image_spec)
        safe_vmname = storage_safe_encode(vm_name)
        safe_image_identifier = storage_safe_encode(backing_image.identifier)
        new_image_path = os.path.join(
            self.__vm_dir(vm_name), f"{safe_vmname}-{num}-{safe_image_identifier}"
        )

        if os.path.exists(new_image_path):
            logging.info(f"VM image '{new_image_path}' already exists. Skipping create.")
            return FrontendImageInfo(self.backend, new_image_path)

        logging.info(
            f"Creating VM Image '{new_image_path}' from backing image '{backing_image.path}'"
        )

        utils.run_check_retcode(
            [
                self.backend.qemu_img_bin,
                "create",
                "-f",
                "qcow2",
                "-o",
                f"backing_file={backing_image.path}",
                new_image_path,
            ]
        )

        logging.info(f"VM Image '{new_image_path}' created")
        return FrontendImageInfo(self.backend, new_image_path)

    def vmstate_exists(self, name: str) -> bool:
        return os.path.exists(self.__vm_dir(name))

    def vmstates(
        self, lock_timeout: Optional[float] = None
    ) -> Iterator[VmPersistentState]:
        for name in os.listdir(self.path):
            try:
                with self.lock_vmstate_by_name(name, timeout=lock_timeout) as state:
                    yield state
            except TransientVmStoreLockHeld:
                continue

    @contextlib.contextmanager
    def lock_vmstate_by_name(
        self, name: str, timeout: Optional[float] = None
    ) -> Iterator[VmPersistentState]:
        config = None
        dir = self.__vm_dir(name)

        if not os.path.exists(dir):
            raise utils.TransientError(msg=f"No VM with name '{name}' found")
        elif not os.path.exists(os.path.join(dir, "config")):
            raise utils.TransientError(
                msg=f"VM with name '{name}' is missing configuration"
            )

        cfg_path = os.path.join(dir, "config")

        try:
            with utils.lock_file(cfg_path, "r", timeout) as cfg_file:
                config = configuration.load_config_file(cast(TextIO, cfg_file), cfg_path)

                images = []
                for filename in os.listdir(dir):
                    path = os.path.join(dir, filename)
                    if filename == "config":
                        continue
                    else:
                        images.append(FrontendImageInfo(self.backend, path))
                yield VmPersistentState(
                    name=name, config=config, images=images, vmstore=self
                )
        except OSError:
            raise TransientVmStoreLockHeld()


class TransientVmStoreLockHeld(utils.TransientError):
    pass