from . import qemu
from . import image
from . import utils
from . import ssh
from . import sshfs

import argparse
import logging
import os
import pwd
import signal
import subprocess
import sys

from typing import cast, Optional, List, Dict, Any, Union


class TransientVm:
    store: image.ImageStore
    config: argparse.Namespace
    vm_images: List[image.FrontendImageInfo]
    ssh_config: Optional[ssh.SshConfig]
    qemu_runner: Optional[qemu.QemuRunner]
    qemu_should_die: bool

    def __init__(self, config: argparse.Namespace, store: image.ImageStore) -> None:
        self.store = store
        self.config = config
        self.vm_images = []
        self.ssh_config = None
        self.qemu_runner = None
        self.qemu_should_die = False

    def __create_images(self, names: List[str]) -> List[image.FrontendImageInfo]:
        return [self.store.create_vm_image(image_name, self.config.name, idx)
                for idx, image_name in enumerate(names)]

    def __needs_ssh(self) -> bool:
        return (self.config.ssh_console is True or
                self.config.ssh_command is not None or
                self.config.ssh_with_serial is True or
                len(self.config.shared_folder) > 0)

    def __needs_ssh_console(self) -> bool:
        return (self.config.ssh_console is True or
                self.config.ssh_with_serial is True or
                self.config.ssh_command is not None)

    def __qemu_added_devices(self) -> List[str]:
        new_args = []
        for image in self.vm_images:
            new_args.extend(["-drive", "file={}".format(image.path)])

        if self.__needs_ssh():
            if self.__needs_ssh_console():
                new_args.append("-nographic")

            if self.config.ssh_port is None:
                ssh_port = utils.allocate_random_port()
            else:
                ssh_port = self.config.ssh_port

            self.ssh_config = ssh.SshConfig(host="localhost",
                                            port=ssh_port,
                                            user=self.config.ssh_user,
                                            ssh_bin_name=self.config.ssh_bin_name)

            # the random localhost port or the user provided port to guest port 22
            new_args.extend([
                "-netdev",
                "user,id=transient-sshdev,hostfwd=tcp::{}-:22".format(ssh_port),
                "-device",
                "e1000,netdev=transient-sshdev"
            ])

        return new_args

    def __connect_ssh(self) -> int:
        assert(self.ssh_config is not None)
        assert(self.qemu_runner is not None)

        client = ssh.SshClient(config=self.ssh_config, command=self.config.ssh_command)
        conn = client.connect_stdout(timeout=self.config.ssh_timeout)

        # The SSH connection has been established. Silence the serial console
        self.qemu_runner.silence()

        conn.wait()
        return conn.returncode

    def __current_user(self) -> str:
        return pwd.getpwuid(os.getuid()).pw_name

    def __qemu_guest_shutdown(self, event: qemu.QmpMessage) -> None:
        logging.info("QEMU guest has shutdown. QMP event: {}".format(event))

    def __qemu_sigchld_handler(self, sig, frame) -> None:
        # We register this signal handler after the QEMU start, so these must not be None
        assert(self.qemu_runner is not None)
        assert(self.qemu_runner.proc_handle is not None)

        # We are only interested in the death of the QEMU child
        pid, exit_indicator = os.waitpid(self.qemu_runner.proc_handle.pid, os.WNOHANG)
        if (pid, exit_indicator) == (0, 0):
            # In this case, the processes that sent SIGCHLD was not QEMU
            return
        else:
            # According to the python docs, the exit_indicator is "a 16-bit number,
            # whose low byte is the signal number that killed the process, and whose
            # high byte is the exit status (if the signal number is zero); the high
            # bit of the low byte is set if a core file was produced."
            #
            # Therefore, we check if the least significant 7 bits are unset, and if
            # so, return the high byte. Otherwise, just return 1
            signal_number = exit_indicator & 0x7f
            if signal_number != 0:
                exit_status = 1
            else:
                exit_status = exit_indicator >> 8

            if self.qemu_should_die is True:
                # We have reached a state where QEMU should be exiting (e.g., we have sent
                # the system_shutdown QMP message). So don't error here.
                logging.debug("QEMU process died as expected")
            else:
                logging.error("QEMU Process has died. Exiting")
                sys.exit(exit_status)

    def run(self) -> int:
        # First, download and setup any required disks
        self.vm_images = self.__create_images(self.config.image)

        if self.config.prepare_only is True:
            return 0

        print("Finished preparation. Starting virtual machine")

        added_qemu_args = self.__qemu_added_devices()
        full_qemu_args = added_qemu_args + self.config.qemu_args

        # If we are using the SSH console, we need to do _something_ with QEMU output.
        qemu_quiet, qemu_silenceable = False, False
        if self.__needs_ssh_console():
            if self.config.ssh_with_serial is True:
                qemu_quiet, qemu_silenceable = False, True
            else:
                qemu_quiet, qemu_silenceable = True, False

        # Note that we must _not_ use QMP if we aren't using the SSH connection, because
        # passing the `-qmp` arg causes QEMU to terminate on SIGINT, even when in
        # `-nographic` mode, which is very surprising.
        self.qemu_runner = qemu.QemuRunner(full_qemu_args, quiet=qemu_quiet,
                                           silenceable=qemu_silenceable,
                                           qmp_connectable=self.__needs_ssh_console())

        qemu_proc = self.qemu_runner.start()

        # Register the exit signal handler for the qemu subprocess, then check if it
        # had already died, just in case.
        signal.signal(signal.SIGCHLD, self.__qemu_sigchld_handler)
        qemu_returncode = qemu_proc.poll()
        if qemu_returncode is not None:
            logging.error("QEMU Process has died. Exiting")
            sys.exit(qemu_returncode)

        for shared_spec in self.config.shared_folder:
            assert(self.ssh_config is not None)
            local, remote = shared_spec.split(":")

            # The user almost certainly doesn't intend to pass a relative path,
            # so make it absolute
            absolute_local_path = os.path.abspath(local)
            sshfs.do_sshfs_mount(connect_timeout=self.config.ssh_timeout,
                                 ssh_config=self.ssh_config,
                                 local_dir=absolute_local_path,
                                 remote_dir=remote,
                                 local_user=self.__current_user())

        if self.__needs_ssh_console():
            # Now wait until the QMP connection is established (this should be very fast).
            assert(self.qemu_runner.qmp_client is not None)
            self.qemu_runner.qmp_client.connect()

            returncode = self.__connect_ssh()

            # In theory, we could get SIGCHLD from the QEMU process before getting or
            # processing the SHUTDOWN event. So set this flag so we don't do the
            # SIGCHLD exit.
            self.qemu_should_die = True

            # If we get a guest SHUTDOWN signal, invoke a callback to log it
            self.qemu_runner.qmp_client.register_callback(
                "SHUTDOWN", self.__qemu_guest_shutdown)

            # Now actually request that the guest shutdown via ACPI
            self.qemu_runner.qmp_client.send_sync(
                {"execute": "system_powerdown"})

            try:
                # Wait a bit for the guest to finish the shutdown and QEMU to exit
                self.qemu_runner.wait(timeout=self.config.shutdown_timeout)

                # If QEMU terminates (as expected), retun the SSH exit code
                return returncode
            except subprocess.TimeoutExpired:
                # if the timeout == 0, then the user expects the guest to not actually
                # shutdown, so don't show an error here.
                if self.config.shutdown_timeout > 0:
                    logging.error(
                        "Timeout expired while waiting for guest to shutdown (timeout={})"
                        .format(self.config.shutdown_timeout))

            # If we didn't reach the expected shutdown, this will terminte
            # the VM. Otherwise, this does nothing.
            self.qemu_runner.terminate()

            # Note that we always return the SSH exit code, even if the guest failed to
            # shut down. This ensures the shutdown_timeout=0 case is handled as expected.
            # (i.e., it returns the SSH code instead of a QEMU error)
            return returncode
        else:
            return self.qemu_runner.wait()
