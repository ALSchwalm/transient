from . import qemu
from . import image

from typing import Optional, List, Dict, Any, Union

class TransientVm:
    store: image.ImageStore
    config: Dict[str, Any]
    vm_images: List[image.ImageInfo]

    def __init__(self, config: Dict[str, Any]) -> None:
        self.store = image.ImageStore()
        self.config = config
        self.vm_images = []

    def __create_images(self, names: List[str]) -> List[image.ImageInfo]:
        return [self.store.create_vm_image(image_name, self.config["name"])
                for image_name in names]

    def __format_new_qemu_args(self) -> List[str]:
        new_args = []
        for image in self.vm_images:
            new_args.extend(["-drive", "file={}".format(image.path())])
        return new_args

    def run(self) -> None:
        # First, download and setup any required disks
        self.vm_images = self.__create_images(self.config["image"])

        added_qemu_args = self.__format_new_qemu_args()
        final_qemu_args = added_qemu_args + self.config["qemu_args"]

        runner = qemu.QemuRunner(final_qemu_args)

        runner.start()

        # TODO: setup shared folders if required
        # TODO: do ssh instead of wait if -ssh-console is passed

        runner.wait()
