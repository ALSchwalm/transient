import ctypes

from typing import cast

PR_SET_PDEATHSIG = 1

_PRCTL_SYSCALL = 157


def prctl(option: int, arg2: int = 0, arg3: int = 0, arg4: int = 0, arg5: int = 0) -> int:
    prctl = ctypes.CDLL(None).syscall
    prctl.restype = ctypes.c_int
    prctl.argtypes = (
        ctypes.c_long,  # The actual syscall number
        ctypes.c_int,
        ctypes.c_ulonglong,
        ctypes.c_ulonglong,
        ctypes.c_ulonglong,
        ctypes.c_ulonglong,
    )
    return cast(int, prctl(_PRCTL_SYSCALL, option, arg2, arg3, arg4, arg5))


def set_death_signal(signal: int) -> int:
    """Send `signal` to this process when the parent dies"""
    return prctl(PR_SET_PDEATHSIG, signal)
