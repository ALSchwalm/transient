from . import qemu
from . import image
from . import utils
from . import ssh
from . import sshfs
from . import static

import argparse
import enum
import glob
import logging
import os
import pwd
import signal
import subprocess
import uuid

from typing import cast, Optional, List, Dict, Any, Union, Tuple, TYPE_CHECKING

# _Environ is declared as generic in stubs but not at runtime. This makes it
# non-subscriptable and will result in a runtime error. According to the
# MyPy documentation, we can bypass this: https://tinyurl.com/snqhqbr
if TYPE_CHECKING:
    Environ = os._Environ[str]
else:
    Environ = os._Environ


class TransientProcessError(Exception):
    returncode: int

    def __init__(self, returncode: int):
        self.returncode = returncode


@enum.unique
class TransientVmState(enum.Enum):
    WAITING = (1,)
    RUNNING = (2,)
    FINISHED = (3,)


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
        self.name = self.config.name or self.__generate_tmp_name()
        self.state = TransientVmState.WAITING

    def __generate_tmp_name(self) -> str:
        return str(uuid.uuid4())

    def __create_images(self, names: List[str]) -> List[image.FrontendImageInfo]:
        return [
            self.store.create_vm_image(image_name, self.name, idx)
            for idx, image_name in enumerate(names)
        ]

    def __needs_ssh(self) -> bool:
        return (
            self.config.ssh_console is True
            or self.config.ssh_command is not None
            or self.config.ssh_with_serial is True
            or len(self.config.shared_folder) > 0
        )

    def __needs_ssh_console(self) -> bool:
        return (
            self.config.ssh_console is True
            or self.config.ssh_with_serial is True
            or self.config.ssh_command is not None
        )

    def __has_readable_kernel(self) -> bool:
        kernels = glob.glob("/boot/vmlinuz-*")
        if len(kernels) == 0:
            logging.debug(f"No kernels found")
            return False
        for kernel in kernels:
            if os.access(kernel, os.R_OK) is True:
                logging.debug(f"Found readable kernel at {kernel}")
                return True
        logging.debug(f"No readable kernels found")
        return False

    def __extract_libguestfs_kernel(self) -> Tuple[str, str]:
        """Extract the transient kernel and modules"""
        home = utils.transient_data_home()
        kernel_destination = os.path.join(home, "transient-kernel")
        modules_destination = os.path.join(home, "transient-modules")
        modules_dep = os.path.join(modules_destination, "modules.dep")
        if os.path.exists(kernel_destination) and os.path.exists(modules_dep):
            logging.debug(f"Transient kernel and modules already extracted. Skipping")
            return kernel_destination, modules_destination

        logging.info(f"Extracting transient kernel to {kernel_destination}")
        utils.extract_static_file("transient-kernel", kernel_destination)

        logging.info(f"Extracting transient modules to {modules_destination}")
        # Our kernel doesn't actually use modules, but libguestfs expects _some_
        # sort of modules directory, so just make an empty one
        os.makedirs(modules_destination)
        with open(modules_dep, "wb+") as f:
            pass
        return kernel_destination, modules_destination

    def __prepare_libguestfs_environment(self) -> Environ:
        """Configures an environment for running libguestfs commands"""
        env = os.environ

        # On platforms that don't have an available kernel or the kernel is
        # not readable (e.g., docker and ubuntu), use ours.
        if not self.__has_readable_kernel():
            logging.info(f"No readable kernel detected. Extracting transient kernel")
            kernel, modules = self.__extract_libguestfs_kernel()
            env["SUPERMIN_MODULES"] = modules
            env["SUPERMIN_KERNEL"] = kernel

        # Avoid using libvirt explicitly
        env["LIBGUESTFS_BACKEND"] = "direct"

        # And do verbose logging so we can debug failures
        env["LIBGUESTFS_TRACE"] = "1"
        env["LIBGUESTFS_DEBUG"] = "1"
        return env

    def __do_copy_command(self, cmd: List[str], environment: Environ) -> None:
        cmd_name = cmd[0]
        try:
            handle = subprocess.Popen(
                cmd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, raw_stderr = handle.communicate(timeout=self.config.copy_timeout)
            if handle.poll() == 0:
                return
        except subprocess.TimeoutExpired:
            handle.terminate()
            _, raw_stderr = handle.communicate()
            logging.error(
                f"{cmd_name} timed out after {self.config.copy_timeout} seconds"
            )
        stderr = raw_stderr.decode("utf-8").strip()
        raise RuntimeError(f"{cmd_name} failed: {stderr}")

    def __needs_to_copy_in_files_before_running(self) -> bool:
        """Checks if at least one file or directory on the host needs to be copied into the VM
           before starting the VM
        """
        return self.config.copy_in_before is not None

    def __copy_in_files(self) -> None:
        """Copies the given files or directories (located on the host) into the VM"""
        path_mappings = self.config.copy_in_before
        for path_mapping in path_mappings:
            self.__copy_in(path_mapping)

    def __copy_in(self, path_mapping: str) -> None:
        """Copies the given file or directory (located on the host) into the VM"""
        try:
            host_path, vm_absolute_path = path_mapping.split(":")
        except ValueError:
            raise RuntimeError(
                f"Invalid file mapping: {path_mapping}."
                + " -copy-in-before must be (path/on/host:/absolute/path/on/guest)"
            )

        if not os.path.exists(host_path):
            raise RuntimeError(f"Host path does not exists: {host_path}")

        if not vm_absolute_path.startswith("/"):
            raise RuntimeError(f"Absolute path for guest required: {vm_absolute_path}")

        environment = self.__prepare_libguestfs_environment()
        for vm_image in self.vm_images:
            assert vm_image.backend is not None
            logging.info(
                f"Copying from '{host_path}' to '{vm_image.backend.identifier}:{vm_absolute_path}'"
            )
            self.__do_copy_command(
                ["virt-copy-in", "-a", vm_image.path, host_path, vm_absolute_path],
                environment,
            )

    def __needs_to_copy_out_files_after_running(self) -> bool:
        """Checks if at least one directory on the VM needs to be copied out
           to the host after stopping the VM
        """
        return self.config.copy_out_after is not None

    def __copy_out_files(self) -> None:
        """Copies the given files or directories (located on the guest) onto the host"""
        path_mappings = self.config.copy_out_after
        for path_mapping in path_mappings:
            self.__copy_out(path_mapping)

    def __copy_out(self, path_mapping: str) -> None:
        """Copies the given file or directory (located on the guest) onto the host"""
        try:
            vm_absolute_path, host_path = path_mapping.split(":")
        except ValueError:
            raise RuntimeError(
                f"Invalid file mapping: {path_mapping}."
                + " -copy-out-after must be (/absolute/path/on/guest:path/on/host)"
            )

        if not os.path.isdir(host_path):
            raise RuntimeError(f"Host path does not exist: {host_path}")

        if not vm_absolute_path.startswith("/"):
            raise RuntimeError(f"Absolute path for guest required: {vm_absolute_path}")

        environment = self.__prepare_libguestfs_environment()
        for vm_image in self.vm_images:
            assert vm_image.backend is not None
            logging.info(
                f"Copying from '{vm_image.backend.identifier}:{vm_absolute_path}' to '{host_path}'"
            )
            self.__do_copy_command(
                ["virt-copy-out", "-a", vm_image.path, vm_absolute_path, host_path,],
                environment,
            )

    def __qemu_added_args(self) -> List[str]:
        new_args = ["-name", self.name]

        for image in self.vm_images:
            new_args.extend(["-drive", f"file={image.path}"])

        if self.__needs_ssh():
            if self.__needs_ssh_console():
                new_args.extend(["-serial", "stdio", "-display", "none"])

            if self.config.ssh_port is None:
                ssh_port = utils.allocate_random_port()
            else:
                ssh_port = self.config.ssh_port

            self.ssh_config = ssh.SshConfig(
                host="127.0.0.1",
                port=ssh_port,
                user=self.config.ssh_user,
                ssh_bin_name=self.config.ssh_bin_name,
            )

            # the random localhost port or the user provided port to guest port 22
            new_args.extend(
                [
                    "-netdev",
                    f"user,id=transient-sshdev,hostfwd=tcp::{ssh_port}-:22",
                    "-device",
                    "e1000,netdev=transient-sshdev",
                ]
            )

        return new_args

    def __connect_ssh(self) -> int:
        assert self.ssh_config is not None
        assert self.qemu_runner is not None

        client = ssh.SshClient(config=self.ssh_config, command=self.config.ssh_command)
        conn = client.connect_stdout(timeout=self.config.ssh_timeout)

        conn.wait()
        return conn.returncode

    def __current_user(self) -> str:
        return pwd.getpwuid(os.getuid()).pw_name

    def __qemu_guest_shutdown(self, event: qemu.QmpMessage) -> None:
        logging.info(f"QEMU guest has shutdown. QMP event: {event}")

    def __qemu_sigchld_handler(self, sig: int, frame: Any) -> None:
        # We register this signal handler after the QEMU start, so these must not be None
        assert self.qemu_runner is not None
        assert self.qemu_runner.proc_handle is not None

        # Once we no longer have a QEMU processes (i.e., the VM is 'finished'), it
        # is an error to waitpid on the QEMU pid. However, we may still receive
        # SIGCHLD during image cleanup for example (from the qemu-img calls). So,
        # just return in this case.
        if self.state == TransientVmState.FINISHED:
            return

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
            signal_number = exit_indicator & 0x7F
            if signal_number != 0:
                exit_status = 1
            else:
                exit_status = exit_indicator >> 8

            if self.qemu_should_die is True:
                # We have reached a state where QEMU should be exiting (e.g., we have sent
                # the system_shutdown QMP message). So don't error here.
                logging.debug("QEMU process died as expected")
            else:
                logging.error("QEMU Process has died")

                # NOTE: this will raise an exception if the exit_status is non-zero.
                # otherwise, it will just return None. Because this is a signal handler,
                # returning from this function will not cause the 'run' call to exit.
                self.__post_run(exit_status)

    def __post_run(self, returncode: int) -> None:
        self.state = TransientVmState.FINISHED

        if self.__needs_to_copy_out_files_after_running():
            self.__copy_out_files()

        # If the config name is None, this is a completely temporary VM,
        # so remove the frontend images
        if self.config.name is None:
            logging.info("Cleaning up temporary vm images")
            for image in self.vm_images:
                self.store.delete_image(image)

        if returncode != 0:
            logging.debug(f"VM exited with non-zero code: {returncode}")
            raise TransientProcessError(returncode)
        return None

    def run(self) -> None:
        self.state = TransientVmState.RUNNING

        # First, download and setup any required disks
        self.vm_images = self.__create_images(self.config.image)

        if self.__needs_to_copy_in_files_before_running():
            self.__copy_in_files()

        if self.config.prepare_only is True:
            return self.__post_run(0)

        print("Finished preparation. Starting virtual machine")

        added_qemu_args = self.__qemu_added_args()
        full_qemu_args = added_qemu_args + list(self.config.qemu_args)

        # If we are using the SSH console, we need to do _something_ with QEMU output.
        qemu_quiet, qemu_interactive = False, True
        if self.__needs_ssh_console():
            qemu_interactive = False
            qemu_quiet = not self.config.ssh_with_serial

        # Note that we must _not_ use QMP if we aren't using the SSH connection, because
        # passing the `-qmp` arg causes QEMU to terminate on SIGINT, even when in
        # `-nographic` mode, which is very surprising.
        self.qemu_runner = qemu.QemuRunner(
            full_qemu_args,
            quiet=qemu_quiet,
            interactive=qemu_interactive,
            qmp_connectable=self.__needs_ssh_console(),
        )

        qemu_proc = self.qemu_runner.start()

        # Register the exit signal handler for the qemu subprocess, then check if it
        # had already died, just in case.
        signal.signal(signal.SIGCHLD, self.__qemu_sigchld_handler)
        qemu_returncode = qemu_proc.poll()
        if qemu_returncode is not None:
            logging.error("QEMU Process has died. Exiting")
            return self.__post_run(qemu_returncode)

        for shared_spec in self.config.shared_folder:
            assert self.ssh_config is not None
            local, remote = shared_spec.split(":")

            # The user almost certainly doesn't intend to pass a relative path,
            # so make it absolute
            absolute_local_path = os.path.abspath(local)
            sshfs.do_sshfs_mount(
                connect_timeout=self.config.ssh_timeout,
                ssh_config=self.ssh_config,
                local_dir=absolute_local_path,
                remote_dir=remote,
                local_user=self.__current_user(),
            )

        if self.__needs_ssh_console():
            # Now wait until the QMP connection is established (this should be very fast).
            assert self.qemu_runner.qmp_client is not None
            self.qemu_runner.qmp_client.connect(self.config.qmp_timeout)

            # Note that we always return the SSH exit code, even if the guest failed to
            # shut down. This ensures the shutdown_timeout=0 case is handled as expected.
            # (i.e., it returns the SSH code instead of a QEMU error)
            returncode = self.__connect_ssh()

            # In theory, we could get SIGCHLD from the QEMU process before getting or
            # processing the SHUTDOWN event. So set this flag so we don't do the
            # SIGCHLD exit.
            self.qemu_should_die = True

            # If we get a guest SHUTDOWN signal, invoke a callback to log it
            self.qemu_runner.qmp_client.register_callback(
                "SHUTDOWN", self.__qemu_guest_shutdown
            )

            # Now actually request that the guest shutdown via ACPI
            self.qemu_runner.qmp_client.send_sync({"execute": "system_powerdown"})

            try:
                # Wait a bit for the guest to finish the shutdown and QEMU to exit
                self.qemu_runner.wait(timeout=self.config.shutdown_timeout)

            except subprocess.TimeoutExpired:
                # if the timeout == 0, then the user expects the guest to not actually
                # shutdown, so don't show an error here.
                if self.config.shutdown_timeout > 0:
                    logging.error(
                        "Timeout expired while waiting for guest to shutdown (timeout={})".format(
                            self.config.shutdown_timeout
                        )
                    )

                # If we didn't reach the expected shutdown, this will terminte
                # the VM. Otherwise, this does nothing.
                self.qemu_runner.terminate()

            # Note that we always return the SSH exit code, even if the guest failed to
            # shut down. This ensures the shutdown_timeout=0 case is handled as expected.
            # (i.e., it returns the SSH code instead of a QEMU error)
            return self.__post_run(returncode)
        else:
            returncode = self.qemu_runner.wait()
            return self.__post_run(returncode)
