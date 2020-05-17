import logging
import signal
import subprocess

from typing import List, Optional

from . import linux


class QemuRunner:
    bin_name: str
    args: List[str]
    quiet: bool

    # As far as I can tell, this _has_ to be quoted. Otherwise, it will
    # fail at runtime because I guess something is actually run here and
    # subprocess.Popen is not actually subscriptable.
    proc_handle: 'Optional[subprocess.Popen[bytes]]'

    def __init__(self, args: List[str], *, bin_name: Optional[str] = None,
                 quiet: bool = False) -> None:
        self.bin_name = bin_name or self.__find_qemu_bin_name()
        self.quiet = quiet
        self.args = args
        self.proc_handle = None

    def __find_qemu_bin_name(self) -> str:
        return 'qemu-system-x86_64'

    def start(self) -> None:
        logging.info("Starting qemu process '{}' with arguments '{}'".format(
            self.bin_name, self.args))

        stdio_redirect = None
        if self.quiet is True:
            stdio_redirect = subprocess.DEVNULL

        self.proc_handle = subprocess.Popen(
            [self.bin_name] + self.args,
            stdin=stdio_redirect,
            stdout=stdio_redirect,
            stderr=stdio_redirect,

            # Automatically send SIGTERM to this process when the main Transient
            # process dies
            preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM))

    def wait(self) -> int:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot wait without being started")

        logging.info("Waiting for qemu process to terminate")
        self.proc_handle.wait()
        return self.proc_handle.returncode

    def terminate(self) -> None:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot terminate without being started")
        self.proc_handle.terminate()

    def kill(self) -> None:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot be killed without being started")
        self.proc_handle.kill()

    def returncode(self) -> int:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot get a returncode without being started")
        elif self.proc_handle.poll() is None:
            raise RuntimeError("QemuRunner cannot get a returncode without being exited")
        else:
            return self.proc_handle.returncode
