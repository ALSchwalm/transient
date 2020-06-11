import os

import subprocess
from behave import *
from hamcrest import *

# Wait for a while, as we may be downloading the image as well
VM_WAIT_TIME = 60 * 10
if os.getenv("CI") is not None:
    DEFAULT_TRANSIENT_ARGS = ["-ssh-timeout", "300", "-shutdown-timeout", "300"]
    DEFAULT_QEMU_ARGS = ["-m", "1G", "-smp", "2"]
else:
    DEFAULT_TRANSIENT_ARGS = []
    DEFAULT_QEMU_ARGS = ["-m", "1G", "-smp", "2", "-enable-kvm", "-cpu", "host"]


def build_command(context):
    config = context.vm_config
    command = [
        "transient",
        *config["transient-early-args"],
        config["command"],
        *config["transient-args"],
    ]
    command.extend(["--", *config["qemu-args"]])
    return command


def run_vm(context):
    command = build_command(context)
    handle = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    context.command_ran = " ".join(command)
    context.handle = handle
    return context.handle


def wait_on_vm(context, timeout=VM_WAIT_TIME):
    context.handle.wait(timeout)
    context.stdout = context.handle.stdout.read().decode("utf-8")
    context.stderr = context.handle.stderr.read().decode("utf-8")


@given("a transient vm")
def step_impl(context):
    context.vm_config = {
        "command": "run",
        "transient-early-args": [],
        "transient-args": list(DEFAULT_TRANSIENT_ARGS),
        "qemu-args": list(DEFAULT_QEMU_ARGS),
    }


@given("a transient delete command")
def step_impl(context):
    context.vm_config = {
        "command": "delete",
        "transient-early-args": [],
        "transient-args": ["-force"],
        "qemu-args": [],
    }


@given('a name "{name}"')
def step_impl(context, name):
    context.vm_config["transient-args"].extend(["-name", name])


@given('a disk image "{image}"')
def step_impl(context, image):
    context.vm_config["transient-args"].extend(["-image", image])


@given("a ssh console")
def step_impl(context):
    context.vm_config["transient-args"].extend(["-ssh-console"])


@given("a ssh-with-serial console")
def step_impl(context):
    context.vm_config["transient-args"].extend(["-ssh-with-serial"])


@given('a ssh command "{command}"')
@when('a new ssh command "{command}"')
def step_impl(context, command):
    context.vm_config["transient-args"].extend(["-ssh-command", command])


@given("the vm is prepare-only")
def step_impl(context):
    context.vm_config["transient-args"].extend(["-prepare-only"])


@given('a frontend "{frontend}"')
def step_impl(context, frontend):
    context.vm_config["transient-args"].extend(["-image-frontend", frontend])
    context.vm_config["image-frontend"] = frontend


@given('a backend "{backend}"')
def step_impl(context, backend):
    context.vm_config["transient-args"].extend(["-image-backend", backend])
    context.vm_config["image-backend"] = backend


@given('a sshfs mount of "{mount}"')
def step_impl(context, mount):
    context.vm_config["transient-args"].extend(["-shared-folder", mount])


@given('a transient flag "{flag}"')
def step_impl(context, flag):
    context.vm_config["transient-args"].append(flag)


@given('a transient early flag "{flag}"')
def step_impl(context, flag):
    context.vm_config["transient-early-args"].append(flag)


@given('a guest test file: "{}"')
@given('a guest directory: "{}"')
def step_impl(context, guest_path):
    context.vm_config["guest-path"] = guest_path


@given('a test file: "{}/{}"')
def step_impl(context, host_directory, test_file_name):
    os.makedirs(host_directory, exist_ok=True)
    test_file_path = os.path.join(host_directory, test_file_name)
    open(test_file_path, "w").close()
    context.vm_config["test-file"] = test_file_path


@given('a host directory: "{}"')
def step_impl(context, host_directory):
    context.vm_config["host-directory"] = host_directory
    os.makedirs(host_directory, exist_ok=True)


@given("the test file is copied to the guest directory before starting")
def step_impl(context):
    directory_mapping = "{}:{}".format(
        context.vm_config["test-file"], context.vm_config["guest-path"]
    )
    context.vm_config["transient-args"].extend(["-copy-in-before", directory_mapping])


@given("the guest test file is copied to the host directory after stopping")
def step_impl(context):
    directory_mapping = "{}:{}".format(
        context.vm_config["guest-path"], context.vm_config["host-directory"]
    )
    context.vm_config["transient-args"].extend(["-copy-out-after", directory_mapping])


@given('a qemu flag "{flag}"')
def step_impl(context, flag):
    context.vm_config["qemu-args"].append(flag)


@when("the vm runs to completion")
@when("the transient command is run")
def step_impl(context):
    run_vm(context)
    wait_on_vm(context)


@when("the vm runs")
def step_impl(context):
    run_vm(context)


@when("the vm is provided stdin")
def step_impl(context):
    text = context.text + "\n"
    context.handle.stdin.write(text.encode("utf-8"))
    context.handle.stdin.close()


@when("we wait for the vm to exit")
def step_impl(context):
    wait_on_vm(context)


@then("the return code is {code}")
def step_impl(context, code):
    if context.handle.returncode != int(code):
        print("command stdout:")
        print(context.stdout)
        print("command stderr:")
        print(context.stderr)
    print(f"Command run was {context.command_ran}")
    assert_that(context.handle.returncode, equal_to(int(code)))


@then('stdout contains "{expected_stdout}"')
def step_impl(context, expected_stdout):
    assert_that(context.stdout, contains_string(expected_stdout))


@then('stderr contains "{expected_stderr}"')
def step_impl(context, expected_stderr):
    assert_that(context.stderr, contains_string(expected_stderr))


@then('the file "{name}" is in the backend')
def step_impl(context, name):
    items = os.listdir(context.vm_config["image-backend"])
    assert_that(items, has_item(name))


@then('the file "{name}" is not in the backend')
def step_impl(context, name):
    items = os.listdir(context.vm_config["image-backend"])
    assert_that(items, not_(has_item(name)))


@then('the file "{name}" is in the frontend')
def step_impl(context, name):
    items = os.listdir(context.vm_config["image-frontend"])
    assert_that(items, has_item(name))


@then('the file "{name}" is not in the frontend')
def step_impl(context, name):
    items = os.listdir(context.vm_config["image-frontend"])
    assert_that(items, not_(has_item(name)))


@then('the file "{file_path}" exists')
def step_impl(context, file_path):
    assert os.path.exists(file_path)
