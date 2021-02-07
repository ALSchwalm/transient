import base64
import beautifultable  # type: ignore
import datetime
import json
import logging
import os
import time
from typing import (
    Optional,
    List,
    Dict,
    Any,
)

from . import ssh
from . import qemu

_PID_ROOT = "/proc"
SCAN_DATA_FD = "__TRANSIENT_DATA_FD"
SCAN_ENVIRON_SENTINEL = "__TRANSIENT_PROCESS"


class TransientInstance:
    pid: int
    start_time: datetime.datetime
    name: Optional[str]
    ssh_port: Optional[int]

    def __init__(self, pid: int, start_time: datetime.datetime, config: Dict[Any, Any]):
        self.name = None
        self.ssh_port = None
        self.__dict__.update(config)
        self.start_time = start_time
        self.pid = pid

    def __repr__(self) -> str:
        return f"TransientInstance(pid={self.pid}, start_time={self.start_time}, ...)"


def _read_pid_environ(pid_dir: str) -> Dict[str, str]:
    raw_environ = open(os.path.join(pid_dir, "environ")).read()
    variables = raw_environ.strip("\0").split("\0")
    environ = {}
    for variable in variables:
        name, value = variable.split("=", maxsplit=1)
        environ[name] = value
    return environ


def _read_pid_start_time(pid_dir: str) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(os.stat(pid_dir).st_ctime)


def _read_pid_data(pid_dir: str, data_fd: int) -> Any:
    with open(os.path.join(pid_dir, "fd", str(data_fd))) as f:
        return json.loads(base64.b64decode(f.read()))


def find_transient_instances(
    name: Optional[str] = None, with_ssh: bool = False, timeout: Optional[int] = None
) -> List[TransientInstance]:
    """Find running transient instances matching the given parameters

       If 'name' is specified, only instances started with a equivalent '-name'
       argument will be returned. 'with_ssh' will filter for instances that
       were started with '-ssh' (or other options that imply '-ssh'). If the
       'timeout' option is passed, this function will block until at least one
       instance matching the provided parameters is found, or a timeout occurs.
       Note that 'timeout' may not be passed by itself.
    """
    if name is None and with_ssh is False and timeout is not None:
        raise RuntimeError(
            f"find_transient_instances: 'timeout' cannot be specified without either 'name' or 'with_ssh'"
        )

    search_start_time = time.time()

    instances = []
    while timeout is None or (time.time() - search_start_time < timeout):
        for proc in os.listdir(_PID_ROOT):
            pid_dir = os.path.join(_PID_ROOT, proc)
            if os.path.isdir(pid_dir) is False:
                continue
            try:
                environ = _read_pid_environ(pid_dir)
            except:
                continue

            if SCAN_ENVIRON_SENTINEL not in environ:
                continue

            start_time = _read_pid_start_time(pid_dir)

            try:
                data = _read_pid_data(pid_dir, int(environ[SCAN_DATA_FD]))
            except json.decoder.JSONDecodeError:
                # A decode error will happen if the entry is scanned between the
                # time the transient instances starts and the data fd is filled
                # with the actual data. Ignore the entry in this case.
                continue

            if name is not None and ("name" not in data or data["name"] != name):
                continue
            if with_ssh is True and "ssh_port" not in data:
                continue
            instances.append(TransientInstance(int(proc), start_time, data))
        if timeout is None or len(instances) > 0:
            break
        else:
            delay_between = ssh.SSH_CONNECTION_TIME_BETWEEN_TRIES
            logging.info(f"Unable to locate VM. Waiting {delay_between}s before retrying")
            time.sleep(delay_between)
    return instances


def format_instance_table(
    instances: List[TransientInstance],
) -> beautifultable.BeautifulTable:
    table = beautifultable.BeautifulTable()
    table.column_headers = ["VM Name", "Start Time", "PID", "SSH Port"]
    table.set_style(beautifultable.BeautifulTable.STYLE_BOX)
    table.column_alignments["VM Name"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["Start Time"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["PID"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments["SSH Port"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    for instance in instances:
        if instance.ssh_port is None:
            port = "N/A"
        else:
            port = str(instance.ssh_port)
        table.append_row([instance.name, instance.start_time, instance.pid, port])
    return table
