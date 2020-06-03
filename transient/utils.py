import distutils.util
import logging
import os
import socket
import tempfile

try:
    import importlib.resources as pkg_resources

    package_read_bytes = pkg_resources.read_binary
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    import importlib_resources as pkg_resources  # type: ignore

    package_read_bytes = pkg_resources.read_binary

from typing import cast, Optional
from . import static


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


def allocate_random_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Binding to port 0 causes the kernel to allocate a port for us. Because
    # it won't reuse that port until is _has_ to, this can safely be used
    # as (for example) the ssh port for the guest and it 'should' be race-free
    s.bind(("", 0))
    addr = s.getsockname()
    s.close()
    return cast(int, addr[1])


_XDG_FALLBACK_DATA_PATH = "/tmp"


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


def extract_static_file(key: str, destination: str) -> None:
    static_file = package_read_bytes(static, key)

    # Set delete=False because we will be moving the file
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(destination), delete=False) as f:
        f.write(static_file)

        # The rename is done atomically, so even if we race with another
        # processes, SSH will definitely get the full file contents
        os.rename(f.name, destination)
