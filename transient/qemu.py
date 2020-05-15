import logging
import subprocess

from typing import List, Optional


class QemuRunner:
    bin_name: str
    args: List[str]

    # As far as I can tell, this _has_ to be quoted. Otherwise, it will
    # fail at runtime because I guess something is actually run here and
    # subprocess.Popen is not actually subscriptable.
    proc_handle: 'Optional[subprocess.Popen[bytes]]'

    def __init__(self, args: List[str], *, bin_name: Optional[str] = None) -> None:
        self.bin_name = bin_name or self.__find_qemu_bin_name()
        self.args = args
        self.proc_handle = None

    def __find_qemu_bin_name(self) -> str:
        return 'qemu-system-x86_64'

    def start(self) -> None:
        logging.info("Starting qemu process '{}' with arguments '{}'".format(
            self.bin_name, self.args))
        self.proc_handle = subprocess.Popen([self.bin_name] + self.args)

    def wait(self) -> None:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot wait without being started")

        logging.info("Waiting for qemu process to terminate")
        self.proc_handle.wait()
