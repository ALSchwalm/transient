import distutils.util
import logging
import itertools
import io
import os
import pathlib
import progressbar  # type: ignore
import select
import socket
import subprocess
import time
import tempfile
import uuid

try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    import importlib_resources as pkg_resources  # type: ignore

from typing import cast, Optional, ContextManager, List, Union, IO, Any, Tuple
from . import static

# From the typeshed Popen definitions
FILE_TYPE = Union[None, int, IO[Any]]


def prompt_yes_no(prompt: str, default: Optional[bool] = None) -> bool:
    if default is True:
        indicator = "[Y/n]"
    elif default is False:
        indicator = "[y/N]"
    else:
        indicator = "[y/n]"

    full_prompt = f"{prompt} {indicator}: "
    while True:
        try:
            response = input(full_prompt)
            if response == "" and default is not None:
                return default
            return bool(distutils.util.strtobool(response))
        except ValueError:
            print("Please select Y or N")


def format_bytes(size: float) -> str:
    power = 2 ** 10
    n = 0
    labels = {0: "", 1: "KiB", 2: "MiB", 3: "GiB", 4: "TiB"}
    while size > power:
        size /= power
        n += 1
    return "{:.2f} {}".format(size, labels[n])


def generate_unix_socket_path() -> str:
    id = str(uuid.uuid4())
    return os.path.join(tempfile.gettempdir(), f"transient.{id}")


_XDG_FALLBACK_DATA_PATH = tempfile.gettempdir()


def xdg_data_home() -> str:
    user_home = os.getenv("HOME")
    default_xdg_data_home = None
    if user_home is not None:
        default_xdg_data_home = os.path.join(user_home, ".local", "share")
    xdg_data_home = os.getenv("XDG_DATA_HOME", default_xdg_data_home)

    if xdg_data_home is None:
        logging.warning(
            f"$HOME and $XDG_DATA_HOME not set. Using {_XDG_FALLBACK_DATA_PATH}"
        )
        xdg_data_home = _XDG_FALLBACK_DATA_PATH
    return xdg_data_home


def transient_data_home() -> str:
    return os.path.join(xdg_data_home(), "transient")


def package_file_path(key: str) -> ContextManager[pathlib.Path]:
    return pkg_resources.path(static, key)


def package_file_bytes(key: str) -> bytes:
    return pkg_resources.read_binary(static, key)


def extract_static_file(key: str, destination: str) -> None:
    static_file = package_file_bytes(key)

    directory = os.path.dirname(destination)

    # Ensure the destination directory exists
    os.makedirs(directory, exist_ok=True)

    # Set delete=False because we will be moving the file
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as f:
        f.write(static_file)

        # The rename is done atomically, so even if we race with another
        # processes, we will definitely get the full file contents
        os.rename(f.name, destination)


def join_absolute_paths(path: str, *paths: str) -> str:
    return os.path.join(path, *[p.lstrip("/") for p in paths])


def prepare_file_operation_bar(filesize: int) -> progressbar.ProgressBar:
    return progressbar.ProgressBar(
        maxval=filesize,
        widgets=[
            progressbar.Percentage(),
            " ",
            progressbar.Bar(),
            " ",
            progressbar.FileTransferSpeed(),
            " | ",
            progressbar.DataSize(),
            " | ",
            progressbar.ETA(),
        ],
    )


def read_until(
    source: io.BufferedReader, sentinel: bytes, timeout: Optional[float] = None
) -> bytes:
    """ Read from an IO source until the given sentinel is seen

    This can be thought of as a generalization of IOBase.readline(). When called,
    this method will read bytes from the source until the bytes in 'sentinel'
    are seen. The bytes read will then be returned (including the sentinel). If
    the 'timeout' value is specified, a TimeoutError will be raised if the
    sentinel value is not seen within the given timeout. That exception will
    contain the bytes that had been read at the point the timeout occured.
    """
    start_time = time.time()
    time_remaining = timeout
    buff = b""
    while True:
        (ready, _, _) = select.select([source], [], [], time_remaining)

        # If nothing is ready, then we must have set a timeout and reached it
        if len(ready) == 0:
            assert timeout is not None
            raise TimeoutError(buff)

        waiting = source.peek()
        sentinel_start = (buff + waiting).find(sentinel)

        if sentinel_start != -1:
            if sentinel_start >= len(buff):
                bytes_to_read = sentinel_start - len(buff) + len(sentinel)
            else:
                bytes_to_read = len(sentinel) - (len(buff) - sentinel_start)
            buff += source.read(bytes_to_read)
            return buff
        else:
            # Avoid reading more than we peeked at
            buff += source.read(len(waiting))

        # If we set a timeout, make sure we have time left to try again,
        # otherwise, bail out
        if timeout is not None:
            time_remaining = start_time + timeout - time.time()
            if time_remaining < 0:
                raise TimeoutError(buff)


def copy_with_progress(
    source: IO[bytes],
    destination: IO[bytes],
    bar: Union[progressbar.ProgressBar, int],
    block_size: int = 64 * 1024,
) -> None:
    if isinstance(bar, int):
        prog_bar = prepare_file_operation_bar(bar)
    else:
        prog_bar = bar

    for idx in itertools.count():
        block = source.read(block_size)
        if not block:
            break
        destination.write(block)
        prog_bar.update(idx * block_size)
    prog_bar.finish()


def run_check_retcode(
    cmd: List[str],
    *,
    timeout: Optional[int] = None,
    capture_stdout: bool = True,
    capture_stderr: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    stdout_location: Optional[int] = subprocess.PIPE
    if capture_stdout is False:
        stdout_location = None

    stderr_location: Optional[int] = subprocess.PIPE
    if capture_stderr is False:
        stderr_location = None

    try:
        handle = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=stdout_location,
            stderr=stderr_location,
            check=True,
            timeout=timeout,
        )
        stdout = handle.stdout.decode("utf-8") if handle.stdout is not None else None
        stderr = handle.stderr.decode("utf-8") if handle.stderr is not None else None
        return stdout, stderr
    except subprocess.CalledProcessError as e:
        raise TransientProcessError(
            cmd=e.cmd, returncode=e.returncode, stdout=e.stdout, stderr=e.stderr
        )
    except subprocess.TimeoutExpired as e:
        raise TransientProcessError(cmd=e.cmd, stdout=e.stdout, stderr=e.stderr)


class TransientProcessError(Exception):
    cmd: Optional[str]
    returncode: Optional[int]
    msg: Optional[str]
    stdout: Optional[str]
    stderr: Optional[str]

    def __init__(
        self,
        *,
        cmd: Optional[Union[str, List[str]]] = None,
        returncode: Optional[int] = None,
        msg: Optional[str] = None,
        stdout: Optional[bytes] = None,
        stderr: Optional[bytes] = None,
    ):
        if isinstance(cmd, list):
            self.cmd = " ".join(cmd)
        else:
            self.cmd = cmd
        self.returncode = returncode
        self.msg = msg

        if stdout is not None:
            self.stdout = stdout.decode("utf-8")
        else:
            self.stdout = None

        if stderr is not None:
            self.stderr = stderr.decode("utf-8")
        else:
            self.stderr = None

    def __str__(self) -> str:
        ret = ""
        if self.msg is not None:
            ret += f"{self.msg}: "
        if self.cmd is not None:
            ret += f"{self.cmd}"
        if self.returncode is not None:
            ret += f" exited with return code {self.returncode}"
        if self.stdout is not None:
            ret += f"\n----STDOUT----\n{self.stdout}"
        if self.stderr is not None:
            ret += f"\n----STDERR----\n{self.stderr}"
        return ret
