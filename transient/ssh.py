import copy
import logging
import os
import signal
import subprocess
import time

from typing import Optional, List, IO, Any, Union, Dict, Tuple

from . import linux
from . import utils
from . import static

SSH_CONNECTION_WAIT_TIME = 30
SSH_CONNECTION_TIME_BETWEEN_TRIES = 2
SSH_DEFAULT_CONNECT_TIMEOUT = 3


class SshConfig:
    host: str
    port: int
    ssh_bin_name: str
    args: List[str]
    user: Optional[str]
    password: Optional[str]

    def __init__(
        self,
        host: str,
        port: Optional[int] = None,
        ssh_bin_name: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        args: Optional[List[str]] = None,
    ) -> None:
        self.host = host
        self.port = port if port is not None else 22
        self.user = user
        self.password = password
        self.args = args or []
        self.ssh_bin_name = ssh_bin_name or self.__find_ssh_bin_name()

        # Pass these as default args
        self.args.extend(self.__default_ssh_args())

    def __default_ssh_args(self) -> List[str]:
        return [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "batchMode=yes",
            "-o",
            "LogLevel=ERROR",
            "-o",
            f"ConnectTimeout={SSH_DEFAULT_CONNECT_TIMEOUT}",
        ]

    def __find_ssh_bin_name(self) -> str:
        return "ssh"

    def override(self, **kwargs: Any) -> "SshConfig":
        clone = copy.deepcopy(self)
        if any([key not in self.__dict__ for key in kwargs.keys()]):
            raise RuntimeError("Invalid key word arg to SshConfig.override")
        clone.__dict__.update(kwargs)
        return clone


class SshClient:
    config: SshConfig
    command: Optional[str]

    def __init__(self, config: SshConfig, *, command: Optional[str] = None):
        self.config = config
        self.command = command

    def __prepare_ssh_command(self, user_cmd: Optional[str] = None) -> List[str]:
        if self.config.user is not None:
            host = f"{self.config.user}@{self.config.host}"
        else:
            host = self.config.host

        args = self.config.args + ["-p", str(self.config.port)]

        priv_keys = _prepare_builtin_keys()
        for key in priv_keys:
            args.extend(["-i", key])

        command = [self.config.ssh_bin_name] + args + [host]
        if user_cmd is not None:
            command.append(user_cmd)

        return command

    def __timed_connection(
        self,
        timeout: int,
        ssh_stdin: Optional[utils.FILE_TYPE] = None,
        ssh_stdout: Optional[utils.FILE_TYPE] = None,
        ssh_stderr: Optional[utils.FILE_TYPE] = None,
    ) -> "subprocess.Popen[bytes]":
        probe_command = self.__prepare_ssh_command()
        real_command = self.__prepare_ssh_command(self.command)

        logging.info("Probing SSH using '{}'".format(" ".join(probe_command)))

        start = time.time()
        while time.time() - start < timeout:
            # This process is just used to determine if SSH is available. It is
            # not connected to the requested pipes. Because stdin is connected to
            # /dev/null the connection will be closed automatically (almost) right
            # after it is established, with return code 0.
            completed = subprocess.run(
                probe_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Wait for quite a while, as slow systems (like qemu with a single
                # core and no '-enable-kvm') can take a long time
                timeout=SSH_CONNECTION_WAIT_TIME,
                # Automatically send SIGTERM to this process when the main Transient
                # process dies
                preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM),
            )

            # From the man pages: "ssh exits with the exit status of the
            # remote command or with 255 if an error occurred."
            if completed.returncode == 255:
                stderr = completed.stderr.decode("utf-8").strip()
                logging.info(f"SSH connection failed: {stderr}")
                # In many cases, the command will fail quickly. Avoid spamming tries
                time.sleep(SSH_CONNECTION_TIME_BETWEEN_TRIES)
                continue
            elif completed.returncode == 0:
                logging.info(
                    "Connecting to SSH using command '{}'".format(" ".join(real_command))
                )

                # The connection closed with code 0, which should indicate that ssh is
                # now available in the guest. Now establish another that's connected
                # to the requested stdout/stderr
                proc = subprocess.Popen(
                    real_command,
                    stdin=ssh_stdin,
                    stdout=ssh_stdout,
                    stderr=ssh_stderr,
                    preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM),
                )
                return proc
            else:
                # If the process exited within SSH_CONNECTION_WAIT_TIME seconds with
                # any other return code, that's an exception.
                raise RuntimeError(
                    f"ssh connection failed with return code: {completed.returncode}"
                )
        raise RuntimeError(
            f"Failed to connect with command '{probe_command}' after {timeout} seconds"
        )

    def connect_stdout(self, timeout: int) -> "subprocess.Popen[bytes]":
        return self.__timed_connection(timeout)

    def connect_piped(self, timeout: int) -> "subprocess.Popen[bytes]":
        return self.__timed_connection(
            timeout,
            ssh_stdin=subprocess.PIPE,
            ssh_stdout=subprocess.PIPE,
            ssh_stderr=subprocess.PIPE,
        )

    def connect(
        self,
        timeout: int,
        stdin: Union[None, int, IO[Any]],
        stdout: Union[None, int, IO[Any]],
        stderr: Union[None, int, IO[Any]],
    ) -> "subprocess.Popen[bytes]":
        return self.__timed_connection(timeout, stdin, stdout, stderr)


def _prepare_builtin_keys() -> List[str]:
    home = utils.transient_data_home()
    builtins = {
        "vagrant.priv": os.path.join(home, "vagrant.key"),
        "transient.priv": os.path.join(home, "transient.key"),
    }
    for name, destination in builtins.items():
        if os.path.exists(destination):
            continue

        utils.extract_static_file(name, destination)
    return list(builtins.values())


def scp(
    source: str,
    destination: str,
    config: SshConfig,
    copy_from: bool = False,
    capture_stdout: bool = False,
    capture_stderr: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    if config.user is not None:
        host = f"{config.user}@{config.host}"
    else:
        host = f"{config.host}"

    args = ["-p", "-r", "-P", str(config.port), *config.args]

    priv_keys = _prepare_builtin_keys()
    for key in priv_keys:
        args.extend(["-i", key])

    if copy_from is False:
        host += f":{destination}"
        return utils.run_check_retcode(
            ["scp", *args, source, host],
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
        )
    else:
        host += f":{source}"
        return utils.run_check_retcode(
            ["scp", *args, host, destination],
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
        )
