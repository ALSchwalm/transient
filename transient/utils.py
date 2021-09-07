import bz2
import contextlib
import distutils.util
import fcntl
import logging
import lzma
import io
import os
import pathlib
import progressbar  # type: ignore
import select
import stat
import subprocess
import time
import tempfile
import uuid
import sys
import zlib

try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    import importlib_resources as pkg_resources  # type: ignore

from typing import (
    Optional,
    ContextManager,
    List,
    Union,
    IO,
    Any,
    Tuple,
    Callable,
    Iterator,
)
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
    labels = {0: "B", 1: "KiB", 2: "MiB", 3: "GiB", 4: "TiB"}
    while size >= power:
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


def default_backend_dir() -> str:
    env_specified = os.getenv("TRANSIENT_BACKEND")
    if env_specified is not None:
        return env_specified
    home = transient_data_home()
    return os.path.join(home, "backend")


def default_vmstore_dir() -> str:
    env_specified = os.getenv("TRANSIENT_VMSTORE")
    if env_specified is not None:
        return env_specified
    home = transient_data_home()
    return os.path.join(home, "vmstore")


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


@contextlib.contextmanager
def lock_file(
    path: str, mode: str, timeout: Optional[float] = None, check_interval: float = 0.1
) -> Iterator[IO[Any]]:
    # By default, python 'open' call will truncate writable files. We can't allow that
    # as we don't yet hold the flock (and there is no way to open _and_ flock in one
    # call). So we use os.open to avoid the truncate.
    fd = os.open(path, os.O_RDWR | os.O_CREAT)

    logging.debug(f"Attempting to acquire lock of '{path}'")

    if timeout is not None:
        lock_flags = fcntl.LOCK_EX | fcntl.LOCK_NB
    else:
        lock_flags = fcntl.LOCK_EX

    start = time.time()
    while True:
        try:
            fcntl.flock(fd, lock_flags)
            break
        except OSError:
            logging.info(f"Unable to acquire lock of '{path}'. Waiting {check_interval}")
            assert timeout is not None
            if time.time() - start < timeout:
                time.sleep(check_interval)
                continue
            raise

    logging.debug(f"Lock of '{path}' acquired")

    # Use 'open' like this to ensure the fd is closed (and therefore, that the lock
    # is released)
    with open(fd, mode) as f:
        yield f


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


def make_path_readonly(path: str) -> None:
    os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def copy_with_progress(
    source: IO[bytes],
    destination: IO[bytes],
    bar: Union[progressbar.ProgressBar, int],
    block_size: int = 64 * 1024,
    decompress: bool = False,
) -> None:
    if isinstance(bar, int):
        prog_bar = prepare_file_operation_bar(bar)
    else:
        prog_bar = bar

    if decompress is False:
        # Decompression is a no-op for the plain format
        decompressor = StreamDecompressor(compression_format="plain")
    else:
        # If decompression is requested, determine the format automatically
        decompressor = StreamDecompressor()

    bytes_copied = 0
    while True:
        block = source.read(block_size)
        if not block:
            break
        destination.write(decompressor.decompress(block))
        bytes_copied += len(block)
        prog_bar.update(bytes_copied)
    prog_bar.finish()


class StreamDecompressor:
    decompression_method: Optional[Callable[[bytes], bytes]]

    def __init__(self, compression_format: Optional[str] = None) -> None:
        if compression_format is not None:
            if compression_format == "plain":
                self.decompression_method = self._init_plain_decompressor()
                return
            for (
                (name, _),
                init_decompressor,
            ) in StreamDecompressor.COMPRESSION_MAGIC.items():
                if name == compression_format:
                    self.decompression_method = init_decompressor(self)
                    return
            raise RuntimeError(f"Unknown compression format '{compression_format}'")
        else:
            self.decompression_method = None

    def decompress(self, contents: bytes) -> bytes:
        if self.decompression_method is None:
            for (
                (fmt, magic),
                (init_decompressor),
            ) in StreamDecompressor.COMPRESSION_MAGIC.items():
                if not contents.startswith(magic):
                    continue
                logging.debug(f"Decompressing stream with format '{fmt}'")
                self.decompression_method = init_decompressor(self)
                break
            else:
                logging.debug("Stream not compressed or unknown type")
                self.decompression_method = self._init_plain_decompressor()

        return self.decompression_method(contents)

    def _init_gz_decompressor(self) -> Callable[[bytes], bytes]:
        inner_decompressor = zlib.decompressobj(zlib.MAX_WBITS | 32)

        def decompress_gz(contents: bytes) -> bytes:
            return inner_decompressor.decompress(contents)

        return decompress_gz

    def _init_bz2_decompressor(self) -> Callable[[bytes], bytes]:
        inner_decompressor = bz2.BZ2Decompressor()

        def decompress_bz2(contents: bytes) -> bytes:
            return inner_decompressor.decompress(contents)

        return decompress_bz2

    def _init_xz_decompressor(self) -> Callable[[bytes], bytes]:
        inner_decompressor = lzma.LZMADecompressor()

        def decompress_xz(contents: bytes) -> bytes:
            return inner_decompressor.decompress(contents)

        return decompress_xz

    def _init_plain_decompressor(self) -> Callable[[bytes], bytes]:
        def decompress_plain(contents: bytes) -> bytes:
            return contents

        return decompress_plain

    COMPRESSION_MAGIC = {
        ("gzip", b"\x1f\x8b"): _init_gz_decompressor,
        ("bz2", b"\x42\x5a\x68"): _init_bz2_decompressor,
        ("xz", b"\xfd\x37\x7a\x58\x5a\x00"): _init_xz_decompressor,
    }


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
            encoding="utf-8",
        )
        return handle.stdout, handle.stderr
    except subprocess.CalledProcessError as e:
        raise TransientProcessError(
            cmd=e.cmd, returncode=e.returncode, stdout=e.stdout, stderr=e.stderr
        )
    except subprocess.TimeoutExpired as e:
        raise TransientProcessError(
            cmd=e.cmd, stdout=e.stdout, stderr=e.stderr,
        )
    except FileNotFoundError as e:
        prog = repr(cmd[0])
        raise TransientProcessError(msg=f"Required program {prog} is not installed",)
    except OSError as e:
        # covers "permission denied" and any other reason the OS might refuse
        # to run the binary for us.
        prog = repr(cmd[0])
        err = os.strerror(e.errno)
        raise TransientProcessError(msg=f"Could not run required program {prog}: {err}",)
    except UnicodeDecodeError as e:
        raise TransientProcessError(
            msg=f"Command produced garbage", cmd=cmd,
        )


class TransientError(Exception):
    """
    A runtime error that we have decided to handle by aborting. Exists as a
    separate class for one main reason:

    We can catch errors of this type and print out a nice error message, while
    unexpected ValueErrors and the like can continue making gross stack traces
    to encourage issues submission and make debugging easier.
    """

    def __init__(self, msg: Optional[str] = None):
        self.msg = msg

    def __str__(self) -> str:
        # Subclasses can override if they want to allow msg = None.
        # Assert so that if it ever happens, we'll see a stack trace pointing
        # our way back to the culprit.
        assert self.msg is not None
        return self.msg

    def exit(self) -> None:
        """Exit the program, with an appropriate error code"""
        sys.exit(1)


class TransientProcessError(TransientError):
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
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(msg)
        if isinstance(cmd, list):
            self.cmd = " ".join(cmd)
        else:
            self.cmd = cmd
        self.returncode = returncode

        if stdout is not None:
            self.stdout = stdout
        else:
            self.stdout = None

        if stderr is not None:
            self.stderr = stderr
        else:
            self.stderr = None

    def __str__(self) -> str:
        ret = ""
        if self.msg is not None:
            ret += f"{self.msg}"
            if self.cmd is not None:
                ret += ": "
        if self.cmd is not None:
            ret += f"{self.cmd}"
        if self.returncode is not None:
            ret += f" exited with return code {self.returncode}"
        if self.stdout is not None:
            ret += f"\n----STDOUT----\n{self.stdout}"
        if self.stderr is not None:
            ret += f"\n----STDERR----\n{self.stderr}"
        return ret

    def exit(self) -> None:
        if self.returncode is not None:
            errcode = self.returncode
        else:
            errcode = 1
        sys.exit(errcode)
