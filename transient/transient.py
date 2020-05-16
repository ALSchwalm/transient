from . import qemu
from . import image
from . import ssh

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
        return [self.store.create_vm_image(image_name, self.config["name"], idx)
                for idx, image_name in enumerate(names)]

    def __format_new_qemu_args(self) -> List[str]:
        new_args = []
        for image in self.vm_images:
            new_args.extend(["-drive", "file={}".format(image.path())])

        if self.config["ssh_console"] is True:
            new_args.append("-nographic")

            # Use userspace networking (so no root is needed), and bind
            # localhost port 5555 to guest port 22
            # TODO: try to find an available port
            new_args.extend(["-net", "nic,model=e1000",
                             "-net", "user,hostfwd=tcp::5555-:22"])
        return new_args

    def __connect_ssh(self) -> int:
        client = ssh.SshClient(user=self.config["ssh_user"])
        return client.connect()

    def run(self) -> int:
        # First, download and setup any required disks
        self.vm_images = self.__create_images(self.config["image"])

        added_qemu_args = self.__format_new_qemu_args()
        full_qemu_args = added_qemu_args + self.config["qemu_args"]

        runner = qemu.QemuRunner(full_qemu_args, quiet=self.config["ssh_console"])

        runner.start()

        # TODO: setup shared folders if required

        if self.config["ssh_console"] is True:
            returncode = self.__connect_ssh()

            # Once the ssh connection closes, terminate the VM
            # TODO: signal handler to kill the VM even if `transient`
            # dies unexpectedly.
            runner.terminate()

            # If sigterm didn't work, kill it
            runner.kill()

            # Note that for ssh-console, we return the code of the ssh connection,
            # not the qemu process
            return returncode
        else:
            return runner.wait()
