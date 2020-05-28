import copy
import logging
import signal
import subprocess
import time
import tempfile

from typing import Optional, List, IO, Any, Union

try:
    import importlib.resources as pkg_resources
    _package_read_text = pkg_resources.read_text  # type: ignore
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    import importlib_resources as pkg_resources  # type: ignore
    _package_read_text = pkg_resources.read_text  # type: ignore

from . import linux
from . import vagrant_keys

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

    def __init__(self, host: str, port: Optional[int], ssh_bin_name: Optional[str],
                 user: Optional[str] = None, password: Optional[str] = None,
                 args: Optional[List[str]] = None) -> None:
        self.host = host
        self.port = port if port is not None else 22
        self.user = user
        self.password = password
        self.args = args or []
        self.ssh_bin_name = ssh_bin_name or self.__find_ssh_bin_name()

        # Pass these as default args
        self.args.extend(self.__default_ssh_args())

    def __default_ssh_args(self) -> List[str]:
        return ["-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "batchMode=yes",
                "-o", "LogLevel=ERROR",
                "-o", "ConnectTimeout={}".format(SSH_DEFAULT_CONNECT_TIMEOUT)]

    def __find_ssh_bin_name(self) -> str:
        return "ssh"

    def override(self,
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 ssh_bin_name: Optional[str] = None,
                 user: Optional[str] = None,
                 password: Optional[str] = None,
                 args: Optional[List[str]] = None) -> 'SshConfig':
        clone = copy.deepcopy(self)
        if host is not None:
            clone.host = host
        if port is not None:
            clone.port = port
        if ssh_bin_name is not None:
            clone.ssh_bin_name = ssh_bin_name
        if user is not None:
            clone.user = user
        if password is not None:
            clone.password = password
        if args is not None:
            clone.args = args
        return clone


class SshClient:
    config: SshConfig
    command: Optional[str]
    prepared_keys: Optional[List[str]]

    def __init__(self, config: SshConfig, *, command: Optional[str] = None):
        self.config = config
        self.command = command
        self.prepared_keys = None

    def __prepare_builtin_keys(self) -> List[str]:
        if self.prepared_keys is not None:
            return self.prepared_keys
        vagrant_priv = _package_read_text(vagrant_keys, 'vagrant')
        _, vagrant_priv_file = tempfile.mkstemp()
        with open(vagrant_priv_file, "w") as f:
            f.write(vagrant_priv)

        self.prepared_keys = [vagrant_priv_file]
        return self.prepared_keys

    def __prepare_ssh_command(self, user_cmd: Optional[str] = None) -> List[str]:
        if self.config.user is not None:
            host = "{}@{}".format(self.config.user, self.config.host)
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

    def __timed_connection(self, timeout: int,
                           ssh_stdin: Optional[_FILE] = None,
                           ssh_stdout: Optional[_FILE] = None,
                           ssh_stderr: Optional[_FILE] = None) -> 'subprocess.Popen[bytes]':
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
                preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM))

            # Wait for quite a while, as slow systems (like qemu with a single
            # core and no '-enable-kvm') can take a long time
            returncode = proc.wait(SSH_CONNECTION_WAIT_TIME)

            # From the man pages: "ssh exits with the exit status of the
            # remote command or with 255 if an error occurred."
            if returncode == 255:
                _, raw_stderr = proc.communicate()
                stderr = raw_stderr.decode("utf-8").strip()
                logging.info("SSH connection failed: {}".format(stderr))
                # In many cases, the command will fail quickly. Avoid spamming tries
                time.sleep(SSH_CONNECTION_TIME_BETWEEN_TRIES)
                continue
            elif returncode == 0:
                # The connection closed with code 0, which should indicate that ssh is
                # now available in the guest. Now kill this connection and establish
                # another that's connected to the requested stdout/stderr
                proc.terminate()

                logging.info("Connecting to SSH using command '{}'".format(
                    " ".join(real_command)))

                proc = subprocess.Popen(
                    real_command,
                    stdin=ssh_stdin,
                    stdout=ssh_stdout,
                    stderr=ssh_stderr,
                    preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM))
                return proc
            else:
                # If the process exited within SSH_CONNECTION_WAIT_TIME seconds with
                # any other return code, that's an exception.
                raise RuntimeError("ssh connection failed with return code: {}".format(
                    returncode))
        raise RuntimeError("Failed to connect with command '{}' after {} seconds".format(
            probe_command, timeout))

    def connect_stdout(self, timeout: int) -> 'subprocess.Popen[bytes]':
        return self.__timed_connection(timeout)

    def connect_piped(self, timeout: int) -> 'subprocess.Popen[bytes]':
        return self.__timed_connection(timeout,
                                       ssh_stdin=subprocess.PIPE,
                                       ssh_stdout=subprocess.PIPE,
                                       ssh_stderr=subprocess.PIPE)
