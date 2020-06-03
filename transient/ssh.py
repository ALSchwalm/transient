import copy
import logging
import os
import signal
import subprocess
import time

from typing import Optional, List, IO, Any, Union, Dict

from . import linux
from . import utils
from . import static

SSH_CONNECTION_WAIT_TIME = 30
SSH_CONNECTION_TIME_BETWEEN_TRIES = 2
SSH_DEFAULT_CONNECT_TIMEOUT = 3

# From the typeshed Popen definitions
_FILE = Union[None, int, IO[Any]]


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
        port: Optional[int],
        ssh_bin_name: Optional[str],
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

    def __prepare_builtin_keys(self) -> List[str]:
        home = utils.transient_data_home()
        key_destination = os.path.join(home, "vagrant.key")
        if os.path.exists(key_destination):
            return [key_destination]

        utils.extract_static_file("vagrant.priv", key_destination)
        return [key_destination]

    def __prepare_ssh_command(self, user_cmd: Optional[str] = None) -> List[str]:
        if self.config.user is not None:
            host = f"{self.config.user}@{self.config.host}"
        else:
            host = self.config.host

        args = self.config.args + ["-p", str(self.config.port)]

        priv_keys = self.__prepare_builtin_keys()
        for key in priv_keys:
            args.extend(["-i", key])

        command = [self.config.ssh_bin_name] + args + [host]
        if user_cmd is not None:
            command.append(user_cmd)

        return command

    def __timed_connection(
        self,
        timeout: int,
        ssh_stdin: Optional[_FILE] = None,
        ssh_stdout: Optional[_FILE] = None,
        ssh_stderr: Optional[_FILE] = None,
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
            proc = subprocess.Popen(
                probe_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Automatically send SIGTERM to this process when the main Transient
                # process dies
                preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM),
            )

            # Wait for quite a while, as slow systems (like qemu with a single
            # core and no '-enable-kvm') can take a long time
            returncode = proc.wait(SSH_CONNECTION_WAIT_TIME)

            # From the man pages: "ssh exits with the exit status of the
            # remote command or with 255 if an error occurred."
            if returncode == 255:
                _, raw_stderr = proc.communicate()
                stderr = raw_stderr.decode("utf-8").strip()
                logging.info(f"SSH connection failed: {stderr}")
                # In many cases, the command will fail quickly. Avoid spamming tries
                time.sleep(SSH_CONNECTION_TIME_BETWEEN_TRIES)
                continue
            elif returncode == 0:
                # The connection closed with code 0, which should indicate that ssh is
                # now available in the guest. Now kill this connection and establish
                # another that's connected to the requested stdout/stderr
                proc.terminate()

                logging.info(
                    "Connecting to SSH using command '{}'".format(" ".join(real_command))
                )

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
                    f"ssh connection failed with return code: {returncode}"
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
