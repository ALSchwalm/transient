import logging
import re
import subprocess

from typing import Optional, List

from . import ssh

_SSHFS_MAX_RUN_TIME = 2
_SSHFS_MAX_RUN_TIME_SLOW = 20
_PROVISION_TIME = 120
_PROVISION_TIME_SLOW = 300

_RHEL_PROVISION_SCRIPT = b"""
  set -e
  sudo yum install -y epel-release
  sudo yum install -y sshfs
  sync
  exit
"""

_PROVISION_SCRIPTS = {"RHEL": _RHEL_PROVISION_SCRIPT, "FEDORA": _RHEL_PROVISION_SCRIPT}


def _parse_os_release(contents: str) -> List[str]:
    supported = []
    for line in contents.splitlines():
        match = re.match(r"\s*(\w+)\s*=\s*(.*)", line)
        if match is None:
            continue
        key = match.group(1).upper()
        if key not in ("ID", "ID_LIKE"):
            continue
        value = match.group(2).strip().replace('"', "")
        candidates = [v.upper() for v in value.split() if v.upper() in _PROVISION_SCRIPTS]
        supported.extend(candidates)
    return supported


def _do_provision(
    timeout: int,
    provision_config: ssh.SshConfig,
    system_type: str,
    script: bytes,
    is_slow: bool,
) -> bool:
    client = ssh.SshClient(config=provision_config)
    conn = client.connect_piped(timeout)

    print(f"Starting provision of {system_type} type system")

    try:
        provision_timeout = _PROVISION_TIME
        if is_slow is True:
            provision_timeout = _PROVISION_TIME_SLOW
        raw_stdout, raw_stderr = conn.communicate(script, timeout=provision_timeout)
        returncode = conn.poll()

        stdout = raw_stdout.decode("utf-8").strip()
        stderr = raw_stderr.decode("utf-8").strip()

        logging.debug(f"Provisioning output:\n{stdout}")

        if returncode != 0:
            raise RuntimeError(f"Error while provisioning system: {stderr}")
        else:
            print("Provisioning completed")
            return True
    except subprocess.TimeoutExpired:
        conn.terminate()
        raw_stdout, raw_stderr = conn.communicate()
        stdout = raw_stdout.decode("utf-8").strip()
        stderr = raw_stderr.decode("utf-8").strip()

        logging.debug(f"Provisioning output before timeout:\n{stdout}")

        raise RuntimeError(f"Timeout while executing provisioning commands: {stderr}")


def _should_provision(is_provisioned: bool, error: str) -> bool:
    if is_provisioned:
        return False
    else:
        return "sshfs: command not found" in error


def provision_system(timeout: int, ssh_config: ssh.SshConfig, is_slow: bool) -> bool:
    provision_config = ssh_config.override(args=["-T"] + ssh_config.args)

    client = ssh.SshClient(config=provision_config, command="cat /etc/os-release")
    conn = client.connect_piped(timeout)
    raw_stdout, raw_stderr = conn.communicate(timeout=timeout)
    returncode = conn.poll()
    stdout = raw_stdout.decode("utf-8").strip()
    stderr = raw_stderr.decode("utf-8").strip()

    if returncode != 0:
        logging.info(f"Failed to read /etc/os-release: {stderr}")
        return False

    logging.debug(f"Guest /etc/os-release: {stdout}")

    candidates = _parse_os_release(stdout)
    logging.debug(f"Possible system types: {candidates}")

    script = None
    candidate = None
    if len(candidates) > 0:
        # TODO: For now, just use the first one. In the future, maybe we
        # should try each one in turn.
        candidate = candidates[0]
        script = _PROVISION_SCRIPTS[candidate]
    else:
        logging.warning("Unknown system type. Cannot provision.")

    if script is not None:
        assert candidate is not None
        return _do_provision(timeout, provision_config, candidate, script, is_slow)
    return False


def do_sshfs_mount(
    *,
    connect_timeout: int,
    local_dir: str,
    remote_dir: str,
    local_user: str,
    local_password: Optional[str] = None,
    ssh_config: ssh.SshConfig,
    is_provisioned: bool = False,
    is_slow: bool = False,
) -> None:

    sshfs_config = ssh_config.override(
        args=["-A", "-T", "-o", "LogLevel=ERROR",] + ssh_config.args
    )
    client = ssh.SshClient(sshfs_config)
    conn = client.connect_piped(timeout=connect_timeout)

    try:
        sshfs_options = "-o StrictHostKeyChecking=no -o allow_other"
        sshfs_command = f"sudo -E sshfs {sshfs_options} {local_user}@10.0.2.2:{local_dir} {remote_dir}"

        logging.info(f"Sending sshfs mount command '{sshfs_command}'")

        sshfs_timeout = _SSHFS_MAX_RUN_TIME
        if is_slow is True:
            sshfs_timeout = _SSHFS_MAX_RUN_TIME_SLOW

        # This is somewhat gnarly. The core of the issue is that sshfs is a FUSE mount,
        # so it runs as a process (that gets backgrounded by default). SSH won't close
        # the connection on its side until "it encounters end-of-file (eof) on the pipes
        # connecting  to the stdout and stderr of the user program". This typically means
        # you can do something like 'nohup <cmd> >/dev/null </dev/null 2>&1 &' to close
        # all handles and ignore any hang ups. However, this doesn't work for SSHFS, as
        # it spawns other processes that (I guess?) still have an open handle.
        #
        # This causes the SSH connetion to hang forever after the logout. Therefore, we
        # need to close the connection on our end. So the trick here is to wait for some
        # max time for this process to be done, then inspect the stdout for a sentinel
        # value indicating that we _did_ get to the point where it should be OK to
        # terminate the connection.
        #
        # See http://www.snailbook.com/faq/background-jobs.auto.html for some more info.
        _, raw_stderr = conn.communicate(
            input=f"""
          set -e
          sudo mkdir -p {remote_dir}
          {sshfs_command}
          echo TRANSIENT_SSHFS_DONE
          exit
        """.encode(
                "utf-8"
            ),
            timeout=sshfs_timeout,
        )

        # Ensure returncode is set
        conn.poll()

        if conn.returncode == 0:
            # On some platforms, maybe this does actually terminate. If it does,
            # then just return, but warn because something weird is probably happening
            logging.warning("sshfs connection did not cause session hang as expected")
            return

        stderr = raw_stderr.decode("utf-8")

        # Check whether this failure looks like it is the result of the vm being
        # unprovisioned
        if _should_provision(is_provisioned, stderr) is False:
            raise RuntimeError(f"SSHFS mount failed with: {stderr}")

        # If so, try to provision it
        success = provision_system(connect_timeout, ssh_config, is_slow)
        if success is True:
            # Try the sshfs again once we have provisioned the sytem
            do_sshfs_mount(
                connect_timeout=connect_timeout,
                local_dir=local_dir,
                remote_dir=remote_dir,
                local_user=local_user,
                local_password=local_password,
                ssh_config=ssh_config,
                is_provisioned=True,
            )
        else:
            raise RuntimeError(
                f"Unable to provision and SSHFS mount failed with: {stderr}"
            )
    except subprocess.TimeoutExpired:
        # The timeout expired (as expected), but because we 'set -e', this means
        # we must be in the state where we're hanging after the logout. So kill
        # the connection from our end, the sshfs process will continue on the
        # guest side.
        conn.terminate()

        # There is a chance the sshfs process hung, so check for the sentinel text
        raw_stdout, raw_stderr = conn.communicate()
        stdout = raw_stdout.decode("utf-8")
        stderr = raw_stderr.decode("utf-8")
        if "TRANSIENT_SSHFS_DONE" not in stdout:
            if is_slow:
                # We timed out without getting to the 'echo' in the script, even with
                # extra time. Just give up.
                raise RuntimeError(f"SSHFS mount timed out: {stderr}")
            else:
                logging.warning(
                    "sshfs mount did not complete. Trying with longer timeout"
                )
                # Try again with a longer timeout. The system may just be extremely
                # slow (like qemu with 1 core and no kvm acceleration)
                do_sshfs_mount(
                    connect_timeout=connect_timeout,
                    local_dir=local_dir,
                    remote_dir=remote_dir,
                    local_user=local_user,
                    local_password=local_password,
                    ssh_config=ssh_config,
                    is_slow=True,
                )
