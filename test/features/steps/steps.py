import datetime
import os
import subprocess
import tempfile
import time
import shlex
from behave import *
from hamcrest import *
import stat
import sys
import re

import transient.utils

# Wait for a while, as we may be downloading the image as well
VM_WAIT_TIME = 60 * 15
if os.getenv("CI") is not None:
    DEFAULT_TRANSIENT_ARGS = ["--ssh-timeout", "780", "--shutdown-timeout", "500"]
    DEFAULT_QEMU_ARGS = ["-m", "1G", "-smp", "2"]
else:
    DEFAULT_TRANSIENT_ARGS = []
    DEFAULT_QEMU_ARGS = ["-m", "1G", "-smp", "2", "-enable-kvm", "-cpu", "host"]


def build_command(context):
    config = context.vm_config
    # ensure we are running dev version of transient, regardless of PATH.
    command = [
        sys.executable,
        "-m",
        "transient",
        *config["transient-early-args"],
        *config["command"],
    ]

    if "transient-image" in config and config["transient-image"] is not None:
        command.append(config["transient-image"])

    command.extend(config["transient-args"])
    command.extend(["--", *config["qemu-args"]])
    return command


def run_vm(context):
    command = build_command(context)
    print(command)
    env = getattr(context, "environ", None)

    # Use temporary files rather than PIPE, because it may fill and block
    # before we start reading
    context.raw_stdout = tempfile.NamedTemporaryFile("rb+", buffering=0)
    context.raw_stderr = tempfile.NamedTemporaryFile("rb+", buffering=0)
    handle = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=context.raw_stdout,
        stderr=context.raw_stderr,
        env=env,
        bufsize=0,
    )
    context.handle = handle
    context.add_cleanup(handle.terminate)
    return context.handle


def wait_on_vm(context):
    if hasattr(context, "wait_time"):
        timeout = context.wait_time
    else:
        timeout = VM_WAIT_TIME
    context.handle.wait(timeout=timeout)
    context.raw_stdout.seek(0)
    context.raw_stderr.seek(0)
    context.stdout = context.raw_stdout.read().decode("utf-8")
    context.stderr = context.raw_stderr.read().decode("utf-8")
    context.returncode = context.handle.returncode


@given("a transient run command")
def step_impl(context):
    context.vm_config = {
        "command": ["run"],
        "transient-image": None,
        "transient-early-args": [],
        "transient-args": list(DEFAULT_TRANSIENT_ARGS),
        "qemu-args": list(DEFAULT_QEMU_ARGS),
    }


@given("a transient run command with no qemu arguments")
def step_impl(context):
    context.vm_config = {
        "command": ["run"],
        "transient-image": None,
        "transient-early-args": [],
        "transient-args": list(DEFAULT_TRANSIENT_ARGS),
        "qemu-args": [],
    }


@given("a transient image rm command")
def step_impl(context):
    context.vm_config = {
        "command": ["image", "rm"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }


@given("a transient rm command")
def step_impl(context):
    context.vm_config = {
        "command": ["rm"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }


@given("a transient create command")
def step_impl(context):
    context.vm_config = {
        "command": ["create"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }


@given("a transient cp command")
def step_impl(context):
    context.vm_config = {
        "command": ["cp"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }


@given("a transient commit command")
def step_impl(context):
    context.vm_config = {
        "command": ["commit"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }


@given("a transient start command")
def step_impl(context):
    context.vm_config = {
        "command": ["start"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": list(DEFAULT_QEMU_ARGS),
    }


@when('changes to "{vm_name}" are commited as "{image_name}"')
def step_impl(context, vm_name, image_name):
    context.vm_config = {
        "command": ["commit"],
        "transient-early-args": [],
        "transient-args": [vm_name, image_name],
        "qemu-args": [],
    }
    run_vm(context)
    wait_on_vm(context)


@given("the prepare-build make target is run")
def step_impl(context):
    subprocess.run(["make", "prepare-build"])


@given("a transient build command")
def step_impl(context):
    # Build commands can take a _long_ time (when we don't have KVM), so wait
    # a while for them to finish
    context.wait_time = VM_WAIT_TIME * 6
    context.vm_config = {
        "command": ["image", "build"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }


@given('a name "{name}"')
def step_impl(context, name):
    if " ".join(context.vm_config["command"]) in ("rm", "ssh", "commit", "start"):
        context.vm_config["transient-args"].append(name)
    else:
        context.vm_config["transient-args"].extend(["--name", name])


@given('a vm name "{name}"')
def step_impl(context, name):
    context.vm_config["transient-args"].append(name)


@given('an imagefile "{imagefile}"')
def step_impl(context, imagefile):
    context.vm_config["transient-args"].extend(["--file", imagefile])


@given('a build directory "{builddir}"')
def step_impl(context, builddir):
    context.vm_config["transient-args"].append(builddir)


@given('a disk image "{image}"')
def step_impl(context, image):
    context.vm_config["transient-image"] = image


@given('an extra disk image "{image}"')
def step_impl(context, image):
    context.vm_config["transient-args"].extend(["--extra-image", image])


@given("an http alpine disk image")
def step_impl(context):
    context.vm_config[
        "transient-image"
    ] = "alpine_rel3,http=https://github.com/ALSchwalm/transient-baseimages/releases/download/6/alpine-3.13.qcow2.xz"


@given("an http centos disk image")
def step_impl(context):
    context.vm_config[
        "transient-image"
    ] = "centos7_rel3,http=https://github.com/ALSchwalm/transient-baseimages/releases/download/5/centos-7.8.2003.qcow2.xz"


@given("a ssh console")
def step_impl(context):
    context.vm_config["transient-args"].extend(["--ssh-console"])


@given('an extra argument "{arg}"')
def step_impl(context, arg):
    args = shlex.split(arg)
    context.vm_config["transient-args"].extend(args)


@given("a ssh-with-serial console")
def step_impl(context):
    context.vm_config["transient-args"].extend(["--ssh-with-serial"])


@given('a ssh command "{command}"')
@when('a new ssh command "{command}"')
def step_impl(context, command):
    context.vm_config["transient-args"].extend(["--ssh-command", command])


@given('a vmstore "{vmstore}"')
def step_impl(context, vmstore):
    context.vm_config["transient-args"].extend(["--vmstore", vmstore])
    context.vm_config["vmstore"] = vmstore


@given('a backend "{backend}"')
def step_impl(context, backend):
    context.vm_config["transient-args"].extend(["--image-backend", backend])
    context.vm_config["image-backend"] = backend


@given('a sshfs mount of "{mount}"')
def step_impl(context, mount):
    context.vm_config["transient-args"].extend(["--shared-folder", mount])


@given('a transient flag "{flag}"')
@given('an argument "{flag}"')
def step_impl(context, flag):
    context.vm_config["transient-args"].append(flag)


@given('a transient early flag "{flag}"')
def step_impl(context, flag):
    context.vm_config["transient-early-args"].append(flag)


@given('a guest test file: "{guest_path}"')
@given('a guest directory: "{guest_path}"')
def step_impl(context, guest_path):
    context.vm_config["guest-path"] = guest_path


@given('a test file: "{test_file_path}"')
def step_impl(context, test_file_path):
    os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
    open(test_file_path, "w").close()
    context.vm_config["test-file"] = test_file_path


@given('a symbolic link "{test_symlink_path}" to "{target}"')
def step_impl(context, test_symlink_path, target):
    if not os.path.lexists(test_symlink_path):
        os.symlink(target, test_symlink_path)
    context.vm_config["test-file"] = test_symlink_path


@given('a large test file: "{test_file_path}"')
def step_impl(context, test_file_path):
    os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
    with open(test_file_path, "w") as f:
        for _ in range(100):
            f.write("\x00" * 1024 * 1024)
    context.vm_config["test-file"] = test_file_path


@given('a host directory: "{host_directory}"')
def step_impl(context, host_directory):
    context.vm_config["host-directory"] = host_directory
    os.makedirs(host_directory, exist_ok=True)


@given("the test file is copied to the guest directory before starting")
def step_impl(context):
    directory_mapping = "{}:{}".format(
        context.vm_config["test-file"], context.vm_config["guest-path"]
    )
    context.vm_config["transient-args"].extend(["--copy-in-before", directory_mapping])


@given("the guest test file is copied to the host directory after stopping")
def step_impl(context):
    directory_mapping = "{}:{}".format(
        context.vm_config["guest-path"], context.vm_config["host-directory"]
    )
    context.vm_config["transient-args"].extend(["--copy-out-after", directory_mapping])


@given('using the "{image_type}" image for copying')
def step_impl(context, image_type):
    assert image_type in ("same", "dedicated"), repr(image_type)
    if image_type == "same":
        context.vm_config["transient-args"].extend(["--direct-copy"])


@given('a qemu flag "{flag}"')
def step_impl(context, flag):
    context.vm_config["qemu-args"].append(flag)


@given('the config file "{config_file}"')
def step_impl(context, config_file):
    config_file_path = os.path.join("resources/config-files/", config_file)
    context.vm_config["transient-args"].extend(["--config", config_file_path])


@when("the vm runs to completion")
@when("the transient command is run")
def step_impl(context):
    run_vm(context)
    wait_on_vm(context)


@when("the vm runs")
def step_impl(context):
    run_vm(context)


@when('a vm named "{name}" is started')
@when('a vm named "{name}" is started with flags "{flags}"')
def step_impl(context, name, flags=None):
    if flags is not None:
        extra_flags = shlex.split(flags)
    else:
        extra_flags = []
    context.vm_config = {
        "command": ["start"],
        "transient-early-args": [],
        "transient-args": [name, *extra_flags],
        "qemu-args": [],
    }
    run_vm(context)


@when('a transient ssh command "{command}" runs on "{name}"')
@when('a transient ssh command "{command}" runs on "{name}" with "{flag}"')
def step_impl(context, command, name=None, flag=None):
    command = [
        "transient",
        "ssh",
        name,
        "--ssh-timeout",
        str(VM_WAIT_TIME),
        "--ssh-command",
        command,
    ]
    if flag is not None:
        command.append(flag)
    env = getattr(context, "environ", None)
    handle = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    stdout, stderr = handle.communicate(timeout=VM_WAIT_TIME)
    context.stdout = stdout.decode("utf-8")
    context.stderr = stderr.decode("utf-8")
    context.returncode = handle.returncode
    handle.wait()


@when("a transient ps command runs")
@when('a transient ps command runs with "{flag}"')
def step_impl(context, flag=None):
    context.vm_config = {
        "command": ["ps"],
        "transient-early-args": [],
        "transient-args": [],
        "qemu-args": [],
    }
    if flag is not None:
        context.vm_config["transient-args"].append(flag)
    run_vm(context)
    wait_on_vm(context)


@when("the vm is provided stdin")
def step_impl(context):
    text = context.text + "\n"
    context.handle.stdin.write(text.encode("utf-8"))
    context.handle.stdin.flush()


@when("we wait for the vm to exit")
def step_impl(context):
    wait_on_vm(context)


@then("the return code is {code:d}")
@when("the return code is {code:d}")
def step_impl(context, code):
    if context.returncode != int(code):
        print("command stdout:")
        print(context.stdout)
        print("command stderr:")
        print(context.stderr)
    assert_that(context.returncode, equal_to(int(code)))


@then("the return code is nonzero")
@when("the return code is nonzero")
def step_impl(context):
    assert_that(context.returncode, not_(equal_to(0)))


@then("the vm is terminated")
def step_impl(context):
    context.handle.terminate()


@then('stdout contains "{expected_stdout}"')
def step_impl(context, expected_stdout):
    assert_that(context.stdout, contains_string(expected_stdout))


@then('stderr contains "{expected_stderr}"')
def step_impl(context, expected_stderr):
    assert_that(context.stderr, contains_string(expected_stderr))


@then('stderr matches "{regex}"')
def step_impl(context, regex):
    try:
        r = re.compile(regex, re.IGNORECASE)
    except re.error as e:
        assert False, f"Bad regex {regex!r} in step: {e}"

    assert r.search(context.stderr), f"{context.stderr!r} does not match {regex!r}"


@then('the file "{name}" is in the backend')
def step_impl(context, name):
    items = os.listdir(context.vm_config["image-backend"])
    assert_that(items, has_item(name))


@then('the file "{name}" is not in the backend')
def step_impl(context, name):
    items = os.listdir(context.vm_config["image-backend"])
    assert_that(items, not_(has_item(name)))


@then('the file "{name}" is in the vmstore')
def step_impl(context, name):
    path = os.path.join(context.vm_config["vmstore"], name)
    assert os.path.exists(path)


@then('the file "{name}" is not in the vmstore')
def step_impl(context, name):
    items = os.listdir(context.vm_config["vmstore"])
    assert_that(items, not_(has_item(name)))


@then('the file "{file_path}" exists')
def step_impl(context, file_path):
    assert os.path.exists(file_path)


@then('the file "{file_path}" appears within {seconds} seconds')
def step_impl(context, file_path, seconds):
    for _ in range(int(seconds)):
        if os.path.exists(file_path):
            return
        time.sleep(1)
    assert False, f"File {file_path} didn't appear"


@then('"{file_path}" is a socket')
def step_impl(context, file_path):
    info = os.stat(file_path)
    assert stat.S_ISSOCK(info.st_mode), f"File {file_path} is not a socket"


@then("there is no stack trace")
def step_impl(context):
    assert_that(context.stderr, not_(contains_string("Traceback")))


@given('environment variable {name} is set to "{value}"')
def _set_env_var(context, name, value):
    try:
        env = context.environ
    except AttributeError:
        env = os.environ.copy()

    # note: expandvars expands with respect to the current environment, not
    # with respect to context.environ.
    env[name] = os.path.expandvars(value)
    context.environ = env


@given('environment variable {name} is set to ""')
def step_impl(context, name):
    _set_env_var(context, name, "")


@when('stdout contains "{}" within {} seconds')
def step_impl(context, text, wait):
    import io

    with open(context.raw_stdout.name, "rb") as f:
        transient.utils.read_until(
            io.BufferedReader(f), text.encode("utf-8"), timeout=int(wait)
        )
