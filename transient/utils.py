import distutils.util
import socket

from typing import cast, Optional


def prompt_yes_no(prompt: str, default: Optional[bool] = None) -> bool:
    if default is True:
        indicator = "[Y/n]"
    elif default is False:
        indicator = "[y/N]"
    else:
        indicator = "[y/n]"

    full_prompt = "{} {}: ".format(prompt, indicator)
    while True:
        try:
            response = input(full_prompt)
            if response == "" and default is not None:
                return default
            return bool(distutils.util.strtobool(response))
        except ValueError:
            print("Please select Y or N")


def format_bytes(size):
    power = 2**10
    n = 0
    labels = {0: '', 1: 'KiB', 2: 'MiB', 3: 'GiB', 4: 'TiB'}
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
