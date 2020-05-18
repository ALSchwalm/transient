import subprocess
from behave import *
from hamcrest import *

# Wait for a while, as we may be downloading the image as well
VM_WAIT_TIME=120

def build_command(context):
    config = context.vm_config
    command = ["transient"]

    if "name" in config:
        command.extend(["-name", config["name"]])

    if "images" in config:
        command.extend(["-image", *config["images"]])

    if "ssh-command" in config:
        command.extend(["-ssh-command", config["ssh-command"]])

    if "ssh-console" in config:
        command.extend(["-ssh-console"])

    return command

def run_vm(context):
    command = build_command(context)
    handle = subprocess.Popen(command, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    context.handle = handle
    return context.handle

def wait_on_vm(context, timeout=VM_WAIT_TIME):
    context.handle.wait(timeout)
    context.stdout = context.handle.stdout.read().decode('utf-8')
    context.stderr = context.handle.stderr.read().decode('utf-8')

@given('a transient vm')
def step_impl(context):
    context.vm_config = {}

@given('a name "{name}"')
def step_impl(context, name):
    context.vm_config["name"] = name

@given('a disk image "{image}"')
def step_impl(context, image):
    if "images" not in context.vm_config:
        context.vm_config["images"] = [image]
    else:
        context.vm_config["images"].append(image)

@given('a ssh console')
def step_impl(context):
    context.vm_config["ssh-console"] = True

@given('a ssh command "{command}"')
def step_impl(context, command):
    context.vm_config["ssh-command"] = command

@when('the vm runs to completion')
def step_impl(context):
    run_vm(context)
    wait_on_vm(context)

@when('the vm runs')
def step_impl(context):
    run_vm(context)

@when('the vm is provided stdin')
def step_impl(context):
    text = context.text + "\n"
    context.handle.stdin.write(text.encode('utf-8'))
    context.handle.stdin.close()

@when('we wait for the vm to exit')
def step_impl(context):
    wait_on_vm(context)

@then('the return code is {code}')
def step_impl(context, code):
    assert_that(context.handle.returncode, equal_to(int(code)))

@then('stdout contains "{expected_stdout}"')
def step_impl(context, expected_stdout):
    assert_that(context.stdout, contains_string(expected_stdout))
