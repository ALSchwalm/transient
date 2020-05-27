import collections
import logging
import fcntl
import os
import json
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time

from typing import Any, Dict, DefaultDict, List, Optional, Callable, Union

from . import linux
from . import utils

_QMP_CONNECTION_TIMEOUT = 4
_QMP_DELAY_BETWEEN = 0.2
QMP_DEFAULT_SYNC_TIME = 5
QmpMessage = Dict[Any, Any]
QmpCallback = Callable[[QmpMessage], None]


class QmpClient:
    port: int
    sock: socket.socket
    id_callbacks: DefaultDict[int, List[QmpCallback]]
    event_callbacks: DefaultDict[str, List[QmpCallback]]
    current_id: int

    def __init__(self, port: int):
        self.port = port
        self.id_callbacks = collections.defaultdict(list)
        self.event_callbacks = collections.defaultdict(list)
        self.current_id = 0

    def __allocate_id(self) -> int:
        ret = self.current_id
        self.current_id += 1
        return ret

    def __send_msg(self, msg: QmpMessage):
        logging.debug("Sending QMP message: {}".format(msg))
        self.file.write((json.dumps(msg) + "\r\n").encode("utf-8"))
        self.file.flush()

    def connect(self):
        logging.info("Connecting to QMP socket at localhost:{}".format(self.port))
        start = time.time()
        while time.time() - start < _QMP_CONNECTION_TIMEOUT:
            try:
                self.sock = socket.create_connection(("localhost", self.port))
                logging.debug("QMP connection established")

                # Make a file object so we can readline. QMP messages will always
                # be newline delimited, so this gives us framing. Note that we
                # cannot set the socket to be non-blocking if we do this.
                self.file = self.sock.makefile("rwb")

                # Go ahead and enable sending commands
                self.__send_msg({
                    "execute": "qmp_capabilities"
                })

                # Start and drop this reference. Because the thread is a daemon it will
                # be killed when python dies
                thread = threading.Thread(target=self.__start)
                thread.daemon = True
                thread.start()

                return
            except ConnectionRefusedError:
                logging.debug("QMP connection refused. Waiting")
                time.sleep(_QMP_DELAY_BETWEEN)
        raise ConnectionRefusedError(
            "Unable to connect to QMP socket at localhost:{}".format(self.port))

    def __start(self):
        while True:
            msg_json = self.file.readline()
            if msg_json is None or msg_json == b"":
                logging.debug("QEMU closed QMP connection")
                return
            msg = json.loads(msg_json)
            logging.debug("Received QMP message: {}".format(msg))
            if "id" in msg:
                for callback in self.id_callbacks[msg["id"]]:
                    callback(msg)
                # IDs should not be repeated, so clean up the callbacks
                del self.id_callbacks[msg["id"]]
            elif "event" in msg:
                for callback in self.event_callbacks[msg["event"]]:
                    callback(msg)

    def send_async(self, msg: QmpMessage, callback: QmpCallback):
        id = self.__allocate_id()
        msg["id"] = id
        self.register_callback(id, callback)
        self.__send_msg(msg)

    def send_sync(self, msg: QmpMessage,
                  timeout: Optional[float] = QMP_DEFAULT_SYNC_TIME) -> QmpMessage:
        response = None

        # Start the semaphore value at zero to this thread will block. The callback
        # will increment the counter to unblock this thread when the response to
        # this message has been received.
        semaphore = threading.Semaphore(value=0)

        def _sync_callback(received: QmpMessage):
            nonlocal response
            response = received

            # Note that we are 'releasing' a semaphore we have not acquired. This
            # makes more sense if we using the posix semaphore terminology of 'wait'
            # and 'post', which does not imply that this thread has previously
            # 'acquired' the semaphore.
            semaphore.release()

        self.send_async(msg, _sync_callback)
        semaphore.acquire(timeout=timeout)  # type: ignore

        assert(response is not None)
        return response

    def register_callback(self, id_or_event: Union[int, str],
                          callback: QmpCallback):
        if isinstance(id_or_event, int):
            self.id_callbacks[id_or_event].append(callback)
        elif isinstance(id_or_event, str):
            self.event_callbacks[id_or_event].append(callback)
        else:
            raise RuntimeError(
                "Invalid argument to register_callback '{}'".format(id_or_event))


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
        # Start and drop this reference. Because the thread is a daemon it will
        # be killed when python dies
        thread = threading.Thread(target=self.__start, args=(proc_handle,))
        thread.daemon = True
        thread.start()

    def __start(self, proc_handle: 'subprocess.Popen[bytes]'):
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
    qmp_client: QmpClient

    # As far as I can tell, this _has_ to be quoted. Otherwise, it will
    # fail at runtime because I guess something is actually run here and
    # subprocess.Popen is not actually subscriptable.
    proc_handle: 'Optional[subprocess.Popen[bytes]]'

    def __init__(self, args: List[str], *, bin_name: Optional[str] = None,
                 qmp_port: Optional[int] = None, quiet: bool = False,
                 silenceable: bool = False) -> None:
        qmp_port = qmp_port or utils.allocate_random_port()
        self.bin_name = bin_name or self.__find_qemu_bin_name()
        self.quiet = quiet
        self.args = self.__default_args(qmp_port) + args
        self.proc_handle = None
        self.proxy = None
        self.qmp_client = QmpClient(qmp_port)

        if silenceable is True:
            self.proxy = QemuOutputProxy()

    def __default_args(self, port) -> List[str]:
        return ["-qmp", "tcp:localhost:{},server,nowait".format(port)]

    def __find_qemu_bin_name(self) -> str:
        return 'qemu-system-x86_64'

    def start(self) -> 'subprocess.Popen[bytes]':
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
            self.proxy.start(self.proc_handle)
        return self.proc_handle

    def silence(self):
        if self.quiet is True:
            return
        elif self.proxy is not None:
            self.proxy.silence()
        else:
            raise RuntimeError("Attempt to silence QemuRunner that is not silenceable")

    def wait(self, timeout: Optional[int] = None) -> int:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot wait without being started")

        logging.info("Waiting for qemu process to terminate")
        self.proc_handle.wait(timeout=timeout)
        return self.proc_handle.returncode

    def terminate(self) -> None:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot terminate without being started")
        if self.proc_handle.poll():
            self.proc_handle.terminate()

    def kill(self) -> None:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot be killed without being started")
        if self.proc_handle.poll():
            self.proc_handle.kill()

    def returncode(self) -> int:
        if self.proc_handle is None:
            raise RuntimeError("QemuRunner cannot get a returncode without being started")
        elif self.proc_handle.poll() is None:
            raise RuntimeError("QemuRunner cannot get a returncode without being exited")
        else:
            return self.proc_handle.returncode
