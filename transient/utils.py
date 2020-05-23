import distutils.util

from typing import Optional


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
