import logging
import fcntl
import os
import re
import select
import signal
import subprocess
import sys
import threading

from typing import List, Optional

from . import linux


class QemuOutputProxy:
    quiet: bool
    linux_has_started: bool
    buffer: bytes

    def __init__(self):
        self.quiet = False
        self.buffer = b''
        self.linux_has_started = False

    def silence(self):
        self.quiet = True

    def start(self, proc_handle: 'subprocess.Popen[bytes]'):
        assert(proc_handle.stdout is not None)

        # Set the socket to be non-blocking, as we don't want to read in chuncks
        stdout_handle = proc_handle.stdout
        fl = fcntl.fcntl(stdout_handle, fcntl.F_GETFL)
        fcntl.fcntl(stdout_handle, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        # In order to avoid trashing the console with ANSI escape sequences
        # from grub/whatever is running before the kernel, we wait for output
        # that looks like a timestamp before we start actually proxying anything
        timestamp_matcher = re.compile(br'\[[ \d]+\.\d+\]')

        while not self.quiet:
            ready, _, err = select.select([stdout_handle], [], [])

            if len(err) > 0:
                raise RuntimeError("Error during select in QemuOutputProxy")

            ready_handle = ready[0]

            # Just read whatever is available
            raw_content = ready_handle.read()

            # In theory this should never happen due to the select, but just to
            # be safe
            if raw_content is None:
                continue

            if self.linux_has_started is False:
                combined = self.buffer + raw_content
                position = timestamp_matcher.search(combined)
                if position is not None:
                    self.linux_has_started = True

                    # Strip everything in the buffer before the match
                    raw_content = combined[position.span()[0]:]
                    self.buffer = b''
                else:
                    self.buffer = combined
                    continue

            # We cannot hold the print lock, because this thread may die at any
            # point (for example, if a user ctrl-c's). When that happens, if
            # we hold the print lock, the main thread will crash in an ugly way.
            sys.stdout.buffer.write(raw_content)
            sys.stdout.buffer.flush()

        # We are no longer proxying, so close stdout.
        proc_handle.stdout.close()


class QemuRunner:
    bin_name: str
    args: List[str]
    quiet: bool
    proxy: Optional[QemuOutputProxy]

    # As far as I can tell, this _has_ to be quoted. Otherwise, it will
    # fail at runtime because I guess something is actually run here and
    # subprocess.Popen is not actually subscriptable.
    proc_handle: 'Optional[subprocess.Popen[bytes]]'

    def __init__(self, args: List[str], *, bin_name: Optional[str] = None,
                 quiet: bool = False, silenceable: bool = False) -> None:
        self.bin_name = bin_name or self.__find_qemu_bin_name()
        self.quiet = quiet
        self.args = args
        self.proc_handle = None
        self.proxy = None

        if silenceable is True:
            self.proxy = QemuOutputProxy()

    def __find_qemu_bin_name(self) -> str:
        return 'qemu-system-x86_64'

    def start(self) -> None:
        logging.info("Starting qemu process '{}' with arguments '{}'".format(
            self.bin_name, self.args))

        # By default, perform no redirection
        stdin, stdout, stderr = None, None, None

        if self.quiet is True:
            stdin, stdout, stderr = subprocess.DEVNULL, subprocess.DEVNULL, None
        if self.proxy is not None:
            stdin, stdout, stderr = subprocess.DEVNULL, subprocess.PIPE, None

        self.proc_handle = subprocess.Popen(
            [self.bin_name] + self.args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,

            # Automatically send SIGTERM to this process when the main Transient
            # process dies
            preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM))

        if self.proxy is not None:
            # Start and drop this reference. Because the thread is a daemon it will
            # be killed when python dies
            thread = threading.Thread(target=self.proxy.start, args=(self.proc_handle,))
            thread.daemon = True
            thread.start()

    def silence(self):
        if self.quiet is True:
            return
        elif self.proxy is not None:
            self.proxy.silence()
        else:
            raise RuntimeError("Attempt to silence QemuRunner that is not silenceable")

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
