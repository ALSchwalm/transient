import logging
import subprocess
import time
import tempfile

from typing import Optional, List

try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    import importlib_resources as pkg_resources  # type: ignore

from . import vagrant_keys

SSH_TIME_BETWEEN_TRIES = 5


class SshClient:
    host: str
    port: int
    user: Optional[str]
    password: Optional[str]

    def __init__(self, *, host: str = "localhost", port: int = 5555,
                 user: Optional[str] = None, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def __prepare_builtin_keys(self) -> List[str]:
        vagrant_priv = pkg_resources.read_text(vagrant_keys, 'vagrant')
        _, vagrant_priv_file = tempfile.mkstemp()
        with open(vagrant_priv_file, "w") as f:
            f.write(vagrant_priv)
        return [vagrant_priv_file]

    def connect(self, timeout: int = 60) -> int:
        if self.user is not None:
            host = "{}@{}".format(self.user, self.host)
        else:
            host = self.host

        args = ["-p", str(self.port)]

        priv_keys = self.__prepare_builtin_keys()
        for key in priv_keys:
            args.extend(["-i", key])
        command = ["ssh"] + args + [host]

        logging.info("Connecting ssh using command '{}'".format(" ".join(command)))

        start = time.time()
        while time.time() - start < timeout:
            try:
                proc = subprocess.Popen(command, stderr=subprocess.PIPE)
                proc.wait()

                # From the man pages: "ssh exits with the exit status of the
                # remote command or with 255 if an error occurred."
                if proc.returncode != 255:
                    logging.info("SSH connection closed with return code: {}".format(
                        proc.returncode))
                    return proc.returncode

            except Exception as e:
                logging.debug("Failed to connect to ssh: {}".format(e))
            time.sleep(SSH_TIME_BETWEEN_TRIES)
        raise RuntimeError("Failed to connect with command '{}' after {} seconds".format(
            command, timeout))
