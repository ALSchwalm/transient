from . import qemu
from . import image
from . import ssh

import argparse
import os
import pwd
import socket

from typing import cast, Optional, List, Dict, Any, Union


class TransientVm:
    store: image.ImageStore
    config: argparse.Namespace
    vm_images: List[image.ImageInfo]
    ssh_port: Optional[int]
    qemu_runner: Optional[qemu.QemuRunner]

    def __init__(self, config: argparse.Namespace) -> None:
        self.store = image.ImageStore(backend_dir=config.image_backend,
                                      frontend_dir=config.image_frontend)
        self.config = config
        self.vm_images = []
        self.ssh_port = None
        self.qemu_runner = None

    def __create_images(self, names: List[str]) -> List[image.ImageInfo]:
        return [self.store.create_vm_image(image_name, self.config.name, idx)
                for idx, image_name in enumerate(names)]

    def __needs_ssh(self) -> bool:
        return (self.config.ssh_console is True or
                self.config.ssh_command is not None or
                len(self.config.shared_folder) > 0)

    def __needs_ssh_console(self) -> bool:
        return (self.config.ssh_console is True or
                self.config.ssh_command is not None)

    def __qemu_added_devices(self) -> List[str]:
        new_args = []
        for image in self.vm_images:
            new_args.extend(["-drive", "file={}".format(image.path)])

        if self.__needs_ssh():
            if self.__needs_ssh_console():
                new_args.append("-nographic")

            if self.config.ssh_port is None:
                self.ssh_port = self.__allocate_random_port()
            else:
                self.ssh_port = self.config.ssh_port

            # the random localhost port or the user provided port to guest port 22
            new_args.extend([
                "-netdev",
                "user,id=transient-sshdev,hostfwd=tcp::{}-:22".format(self.ssh_port),
                "-device",
                "e1000,netdev=transient-sshdev"
            ])

        return new_args

    def __allocate_random_port(self) -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Binding to port 0 causes the kernel to allocate a port for us. Because
        # it won't reuse that port until is _has_ to, this can safely be used
        # as (for example) the ssh port for the guest and it 'should' be race-free
        s.bind(("", 0))
        addr = s.getsockname()
        s.close()
        return cast(int, addr[1])

    def __connect_ssh(self) -> int:
        assert(self.ssh_port is not None)

        client = ssh.SshClient(host="localhost",
                               port=self.ssh_port,
                               user=self.config.ssh_user,
                               ssh_bin_name=self.config.ssh_bin_name,
                               command=self.config.ssh_command)
        return client.connect_wait(timeout=self.config.ssh_timeout)

    def __current_user(self) -> str:
        return pwd.getpwuid(os.getuid()).pw_name

    def run(self) -> int:
        # First, download and setup any required disks
        self.vm_images = self.__create_images(self.config.image)

        added_qemu_args = self.__qemu_added_devices()
        full_qemu_args = added_qemu_args + self.config.qemu_args

        self.qemu_runner = qemu.QemuRunner(full_qemu_args, quiet=self.__needs_ssh_console())

        self.qemu_runner.start()

        for shared_spec in self.config.shared_folder:
            local, remote = shared_spec.split(":")
            ssh.do_sshfs_mount(timeout=self.config.ssh_timeout,
                               local_dir=local, remote_dir=remote,
                               host="localhost",
                               ssh_bin_name=self.config.ssh_bin_name,
                               remote_user=self.config.ssh_user,
                               local_user=self.__current_user(),
                               port=self.ssh_port)

        if self.__needs_ssh_console():
            returncode = self.__connect_ssh()

            # Once the ssh connection closes, terminate the VM
            self.qemu_runner.terminate()

            # Note that for ssh-console, we return the code of the ssh connection,
            # not the qemu process
            return returncode
        else:
            return self.qemu_runner.wait()
