import logging
import pathlib
import re
import subprocess
import types

from . import configuration
from . import qemu
from . import utils
from . import ssh
from . import static

from typing import (
    cast,
    Any,
    Sequence,
    Callable,
    List,
    Optional,
    Type,
    Tuple,
    Union,
)


def combine_commands(cmds: List[str], allowfail: bool) -> str:
    if allowfail is True:
        return "; ".join(cmds)
    else:
        return " && ".join(cmds)


class Command:
    def run(self) -> Tuple[Optional[str], Optional[str]]:
        ...


class HostCommand(Command):
    # Use 'Any' here, and the cast later to work around:
    # https://github.com/python/mypy/issues/708
    cmd: Any

    def __init__(self, cmd: Callable[[], Tuple[Optional[str], Optional[str]]]):
        self.cmd = cmd

    def run(self) -> Tuple[Optional[str], Optional[str]]:
        return cast(Tuple[Optional[str], Optional[str]], self.cmd())


class GuestCommand(Command):
    cmd: str
    ssh_config: ssh.SshConfig
    connect_timeout: int
    run_timeout: Optional[int]
    stdin: utils.FILE_TYPE
    stdout: Optional[utils.FILE_TYPE]
    stderr: Optional[utils.FILE_TYPE]

    def __init__(
        self,
        cmd: str,
        ssh_config: ssh.SshConfig,
        connect_timeout: int,
        run_timeout: Optional[int] = None,
        stdin: utils.FILE_TYPE = subprocess.DEVNULL,
        capture_stdout: bool = False,
        capture_stderr: bool = False,
    ):
        self.cmd = cmd
        self.ssh_config = ssh_config
        self.connect_timeout = connect_timeout
        self.run_timeout = run_timeout
        self.stdin = stdin
        self.stdout = subprocess.PIPE if capture_stdout is True else None
        self.stderr = subprocess.PIPE if capture_stderr is True else None

    def run(self) -> Tuple[Optional[str], Optional[str]]:
        client = ssh.SshClient(self.ssh_config, command=self.cmd)

        handle = client.connect(
            self.connect_timeout, stdin=self.stdin, stdout=self.stdout, stderr=self.stderr
        )

        raw_stdout, raw_stderr = handle.communicate(timeout=self.run_timeout)
        stdout = raw_stdout.decode("utf-8") if raw_stdout is not None else None
        stderr = raw_stderr.decode("utf-8") if raw_stderr is not None else None

        result = handle.poll()
        if result != 0:
            raise utils.TransientProcessError(
                cmd=self.cmd, returncode=result, stdout=raw_stdout, stderr=raw_stderr
            )
        else:
            return stdout, stderr


class ImageEditor:
    config: configuration.Config
    ssh_config: ssh.SshConfig
    path: str
    skip_mount: bool
    runner: qemu.QemuRunner

    def __init__(
        self, config: configuration.Config, path: str, skip_mount: bool = False
    ) -> None:
        self.config = config
        self.path = path
        self.skip_mount = skip_mount

    def edit(self) -> "ImageEditor":
        self.runner = self._spawn_qemu(self.path)
        assert self.runner.qmp_client is not None

        ssh_port = ssh.find_ssh_port_forward(self.runner.qmp_client)

        self.ssh_config = ssh.SshConfig(host="127.0.0.1", port=ssh_port, user="root")

        if self.skip_mount is True:
            return self

        self._prepare_mount()
        return self

    def close(self) -> None:
        self.runner.shutdown()

    def __enter__(self) -> "ImageEditor":
        return self.edit()

    def __exit__(
        self,
        type: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[types.TracebackType],
    ) -> Optional[bool]:
        self.close()
        return None

    def _read_fstab(self) -> str:
        blkinfo, _ = self.run_command_in_guest(
            "lsblk -no FSTYPE,PATH -P", capture_stdout=True, capture_stderr=True
        )
        assert blkinfo is not None
        for candidate in blkinfo.strip().split("\n"):
            match = re.match(r'FSTYPE="(.*?)" PATH="(.*?)"', candidate)
            assert match is not None
            fstype = match.group(1)
            path = match.group(2)

            # If we don't recognize the partition type, skip it
            if fstype == "":
                continue

            logging.info(f"Attempting to read /etc/fstab from {path} (fstype={fstype})")
            try:
                raw_fstab, _ = self.run_command_in_guest(
                    [
                        f"mount -t {fstype} {path} /mnt > /dev/null",
                        "cat /mnt/etc/fstab",
                        "umount /mnt > /dev/null",
                    ],
                    capture_stdout=True,
                    capture_stderr=True,
                )
                assert raw_fstab is not None
                return raw_fstab
            except Exception as e:
                logging.debug(f"Failed to read /etc/fstab from {path}: {e}")
                continue
        raise RuntimeError("Unable to locate /etc/fstab")

    def _prepare_mount(self) -> None:
        # Activate any volume groups that may exist
        self.run_command_in_guest(
            f"vgchange -ay", allowfail=True, capture_stdout=True, capture_stderr=True
        )

        fstab_contents = self._read_fstab()
        for entry in self._parse_fstab(fstab_contents):
            self.run_command_in_guest(f"mount {entry[0]} -t {entry[2]} /mnt/{entry[1]}")

    def _excluded_mount_fstypes(self) -> List[str]:
        return ["nfs", "cifs", "swap"]

    def _parse_fstab(self, contents: str) -> List[Tuple[str, str, str]]:
        entries: List[Tuple[str, str, str]] = []
        for num, line in enumerate(contents.split("\n")):
            if line.strip() == "" or line.strip().startswith("#"):
                continue

            match = re.match(r"^(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+))?", line)
            assert match is not None

            dev = match.group(1)
            mnt = match.group(2)
            fstype = match.group(3)
            options = match.group(4)

            if fstype.lower() in self._excluded_mount_fstypes():
                logging.info(f"Ignoring fstab line {num} due to fstype '{fstype}'")
                continue
            elif mnt.lower() == "none":
                logging.info(f"Ignoring fstab line {num} due to mount point 'none'")
                continue
            elif options is not None and "noauto" in options:
                logging.info(f"Ignoring fstab line {num} due to 'noauto'")
                continue
            entries.append((dev, mnt, fstype))

        def sort_key(entry: Tuple[str, str, str]) -> int:
            return len(pathlib.Path(entry[1]).parts)

        return sorted(entries, key=sort_key)

    def _spawn_qemu(self, disk: str) -> qemu.QemuRunner:
        with utils.package_file_path(
            "transient-kernel"
        ) as kernel, utils.package_file_path("transient-initramfs") as initramfs:
            qemu_runner = qemu.QemuRunner(
                [
                    # Use kvm if available
                    "-machine",
                    "accel=kvm:tcg",
                    # Arbitrary cpu/mem
                    # TODO: this should be configurable
                    "-smp",
                    "1",
                    "-m",
                    "1G",
                    # Use our kernel/initramfs
                    "-kernel",
                    str(kernel),
                    "-initrd",
                    str(initramfs),
                    "-append",
                    "notsc console=ttyS0 tsc=reliable no_timer_check usbcore.nousb cryptomgr.notests",
                    # Don't require graphics
                    "-serial",
                    "stdio",
                    "-display",
                    "none",
                    "-nographic",
                    # Expose a fake hardware rng for faster boot
                    "-device",
                    "virtio-rng-pci",
                    # Pass the disk through to the guest (using virtio)
                    "-device",
                    "virtio-scsi-pci,id=scsi",
                    "-drive",
                    f"file={disk},id=hd0,if=none",
                    "-device",
                    "scsi-hd,drive=hd0",
                    # Expose the SSH device
                    "-netdev",
                    f"user,id=transient-sshdev,hostfwd=tcp::0-:22",
                    "-device",
                    "virtio-net-pci,netdev=transient-sshdev",
                ],
                quiet=True,
                qmp_connectable=True,
                interactive=False,
            )
            handle = qemu_runner.start()

            # Block until the qmp connection completes so we know it is ok to
            # (potentially) delete the kernel/initramfs
            assert qemu_runner.qmp_client is not None
            qemu_runner.qmp_client.connect(self.config.qmp_timeout)
            return qemu_runner

    def run_command_in_guest(
        self,
        command: Union[str, List[str]],
        allowfail: bool = False,
        capture_stdout: bool = False,
        capture_stderr: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(command, list):
            single_cmd = combine_commands(command, allowfail)
        else:
            single_cmd = command
        try:
            return GuestCommand(
                single_cmd,
                self.ssh_config,
                self.config.ssh_timeout,
                capture_stdout=capture_stdout,
                capture_stderr=capture_stderr,
            ).run()
        except:
            if allowfail is False:
                raise
            return None, None

    def copy_in(self, host_path: str, guest_path: str) -> None:
        ssh.scp(host_path, utils.join_absolute_paths("/mnt", guest_path), self.ssh_config)

    def copy_out(self, guest_path: str, host_path: str) -> None:
        ssh.scp(
            utils.join_absolute_paths("/mnt", guest_path),
            host_path,
            self.ssh_config,
            copy_from=True,
        )
