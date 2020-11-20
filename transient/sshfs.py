import logging
import os
import signal
import shutil
import subprocess
import threading
import inspect

from typing import Optional, List

from . import linux
from . import ssh

MAX_CONCURRENT_SSHFS = 8

_SSHFS_MAX_RUN_TIME = 2


def get_sftp_server(name: str) -> str:
    # sftp-server isn't on the default PATH. This adds the places it gets installed.
    path_addon = ":".join(
        ["/usr/lib/openssh", "/usr/libexec/openssh", "/usr/libexec", "/usr/lib/ssh"]
    )
    path = f'{os.environ.get("PATH", "")}:{path_addon}'

    server = shutil.which(name, path=path)
    if server is None:
        raise RuntimeError(
            f'"{name}" not found in PATH or usual locations. Try pointing -sftp-bin-name to an SFTP server.'
        )
    return server


class SshfsThread(threading.Thread):

    # Slamming the server with 20 connections at once is a good way to break things:
    sshfs_sem = threading.Semaphore(MAX_CONCURRENT_SSHFS)

    def __init__(
        self, ssh_timeout: int, local_dir: str, remote_dir: str, ssh_config: ssh.SshConfig
    ) -> None:
        super().__init__(daemon=True)

        self.is_complete = threading.Event()
        self.exception: Optional[Exception] = None

        self.ssh_timeout = ssh_timeout
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        self.ssh_config = ssh_config

    def wait_for_mount(self) -> None:
        self.is_complete.wait()
        if self.exception:
            raise RuntimeError(f"SSHFS mount failed: {self.exception}")

    def do_mount(self) -> None:
        sshfs_options = "-o slave,allow_other"
        sshfs_command = (
            f"sudo -E sshfs {sshfs_options} :{self.local_dir} {self.remote_dir}"
        )

        # Because sshfs monopolizes stdout, the progress markers go to stderr
        ssh_command = inspect.cleandoc(
            f"""
            set -e
            echo TRANSIENT_SSH_COMPLETE >&2
            sudo mkdir -p {self.remote_dir}

            # Cache these paths to speed up the SSHFS step. Pass/fail doesn't matter.
            which sudo sshfs 2>/dev/null >/dev/null || true

            echo TRANSIENT_SSHFS_STARTING >&2
            {sshfs_command}
            """
        )

        sshfs_config = self.ssh_config.override(
            args=["-T", "-o", "LogLevel=ERROR"] + self.ssh_config.args
        )
        client = ssh.SshClient(sshfs_config, command=ssh_command)

        sftp_proc = subprocess.Popen(
            [get_sftp_server(name=sshfs_config.sftp_server_bin_name), "-e"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            preexec_fn=lambda: linux.set_death_signal(signal.SIGTERM),
        )

        with self.sshfs_sem:
            logging.info(f"Sending sshfs mount command '{sshfs_command}'")
            ssh_proc = client.connect(
                timeout=self.ssh_timeout,
                stdin=sftp_proc.stdout,
                stdout=sftp_proc.stdin,
                stderr=subprocess.PIPE,
            )

            # Everything from here on out simply verifies that nothing went wrong.
            assert ssh_proc.stderr is not None

            first_stderr_line = ssh_proc.stderr.readline().decode("utf-8")
            if "TRANSIENT_SSH_COMPLETE" not in first_stderr_line:
                ssh_proc.kill()
                stderr = first_stderr_line + ssh_proc.communicate()[1].decode("utf-8")
                raise RuntimeError(f"SSH connection failed with: {stderr}")

        second_stderr_line = ssh_proc.stderr.readline().decode("utf-8")
        if "TRANSIENT_SSHFS_STARTING" not in second_stderr_line:
            ssh_proc.kill()
            stderr = second_stderr_line + ssh_proc.communicate()[1].decode("utf-8")
            raise RuntimeError(f"Shared folder prep failed with: {stderr}")

        try:
            # Now that the SSH connection is established, the SSHFS timeout can be very short
            stderr = ssh_proc.communicate(timeout=_SSHFS_MAX_RUN_TIME)[1].decode("utf-8")
        except subprocess.TimeoutExpired:
            # Because SSHFS is communicating over stdin/out of the ssh connection, SSH
            # needs to run for as long as the mount exists. Instead of waiting until the
            # connection is closed, we wait a short time so SSHFS has a chance to fail.
            # Timing out is expected.
            pass
        else:
            sftp_proc.kill()
            raise RuntimeError(f"SSHFS mount failed with: {stderr}")

        # Verify that the server didn't die while communicate() waited for the client
        assert not sftp_proc.poll()

        # Wake up the main thread
        self.is_complete.set()

        if ssh_proc.wait():
            stderr = ssh_proc.communicate()[1].decode("utf-8")
            if "closed by remote host" not in stderr:
                raise RuntimeError(f"SSHFS mount died with: {stderr}")

    def run(self) -> None:
        try:
            self.do_mount()
        except Exception as e:
            self.exception = e
            self.is_complete.set()
            raise
