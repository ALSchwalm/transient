import argparse
import beautifultable  # type: ignore
import logging
import os
import signal
import sys
import uuid

from . import args
from . import configuration
from . import build
from . import store
from . import scan
from . import ssh
from . import transient
from . import utils
from . import qemu
from . import __version__

from typing import (
    List,
    Any,
    Optional,
    Union,
    Callable,
    cast,
    TypeVar,
    Dict,
    Type,
    Tuple,
)

_DEFAULT_TIMEOUT = 2.5
_TERMINATE_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
_COMMIT_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
_START_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
_RM_CHECK_TIMEOUT = 1.0


def set_log_level(verbose: int) -> None:
    log_level = logging.WARNING
    if verbose == 1:
        log_level = logging.INFO
    elif verbose >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s:%(levelname)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_impl(args: argparse.Namespace) -> None:
    """Create (but do not run) a transient virtual machine"""

    config = configuration.create_transient_create_config(vars(args))
    backend = store.BackendImageStore(path=config.image_backend)
    vmstore = store.VmStore(backend=backend, path=config.vmstore)
    name = vmstore.create_vmstate(config)
    print(f"Created VM '{name}'")


def start_impl(args: argparse.Namespace) -> None:
    """Start an existing virtual machine"""
    config = configuration.create_transient_start_config(vars(args))
    backend = store.BackendImageStore(path=config.image_backend)
    vmstore = store.VmStore(backend=backend, path=config.vmstore)

    with vmstore.lock_vmstate_by_name(config.name, _START_CHECK_TIMEOUT) as state:
        run_config = configuration.run_config_from_create_and_start(state.config, config)

    trans = transient.TransientVm(config=run_config, vmstore=vmstore)
    trans.run()


def run_impl(args: argparse.Namespace) -> None:
    """Run a transient virtual machine."""
    config = configuration.create_transient_run_config(vars(args))

    backend = store.BackendImageStore(path=config.image_backend)
    vmstore = store.VmStore(backend=backend, path=config.vmstore)

    trans = transient.TransientVm(config=config, vmstore=vmstore)
    trans.run()


def rm_impl(args: argparse.Namespace) -> None:
    backend = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=backend, path=args.vmstore)

    for name in args.name:
        if args.force is True:
            # Attempt to kill any running VM, just log errors
            try:
                __terminate_vm(name, vmstore, kill=False, verify=True)
            except Exception as e:
                logging.info(f"An error occured while stopping a VM before removal: {e}")

            # If this is a force removal, don't attempt to acquire any locks
            # or load the state.
            vmstore.unsafe_rm_vmstate_by_name(name)
        else:
            vmstore.rm_vmstate_by_name(name, lock_timeout=_RM_CHECK_TIMEOUT)


def __terminate_vm(name: str, vmstore: store.VmStore, kill: bool, verify: bool) -> None:
    instances = scan.find_transient_instances(name=name, vmstore=vmstore.path)
    if len(instances) > 1:
        raise utils.TransientError(
            msg=f"Multiple running VMs with the name '{name}' in the store at {vmstore}"
        )
    elif len(instances) == 0:
        raise utils.TransientError(msg=f"No running VM found with the name '{name}'")

    vm = instances[0]
    if kill is True:
        sig = signal.SIGKILL
    else:
        sig = signal.SIGTERM
    logging.info(f"Sending signal {sig} to PID {vm.transient_pid}")
    os.kill(vm.transient_pid, signal.SIGTERM)

    if verify is False or vm.stateless is True:
        return

    # Termination is totally finished once we can lock the vm state
    with vmstore.lock_vmstate_by_name(name, timeout=_TERMINATE_CHECK_TIMEOUT):
        return


def stop_impl(args: argparse.Namespace) -> None:
    backend = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=backend, path=args.vmstore)

    for name in args.name:
        __terminate_vm(name, vmstore, args.kill is True, verify=False)


def ssh_impl(args: argparse.Namespace) -> None:
    """Connect to a running VM using SSH"""

    if args.wait:
        timeout = args.ssh_timeout
    else:
        timeout = None

    instances = scan.find_transient_instances(
        name=args.name, timeout=timeout, vmstore=args.vmstore
    )
    if len(instances) > 1:
        raise utils.TransientError(
            msg=f"Multiple running VMs with the name '{args.name}' in the store at {args.vmstore}"
        )
    elif len(instances) == 0:
        raise utils.TransientError(msg=f"No running VM found with the name '{args.name}'")
    else:
        instance = instances[0]

    if instance.ssh_port is None:
        raise utils.TransientError(
            msg=f"Running VM '{args.name}' has no known SSH port. Was it started with '--ssh'?",
        )

    ssh_config = ssh.SshConfig(
        host="127.0.0.1",
        user=args.ssh_user,
        ssh_bin_name=args.ssh_bin_name,
        port=instance.ssh_port,
        extra_options=args.ssh_option,
    )
    client = ssh.SshClient(config=ssh_config, command=args.ssh_command)
    connection = client.connect_stdout(args.ssh_timeout)
    sys.exit(connection.wait())


def ps_impl(args: argparse.Namespace) -> None:
    backend = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=backend, path=args.vmstore)

    # Arbitrary max width to avoid line breaks
    table = beautifultable.BeautifulTable(max_width=1000)
    headers = ["NAME", "IMAGE", "STATUS"]

    if args.pid is True:
        headers.append("PID")
    if args.ssh is True:
        headers.append("SSH")

    table.column_headers = headers

    if args.pid is True:
        table.column_alignments["PID"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    if args.ssh is True:
        table.column_alignments["SSH"] = beautifultable.BeautifulTable.ALIGN_RIGHT

    table.set_style(beautifultable.BeautifulTable.STYLE_NONE)
    table.column_alignments["NAME"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["IMAGE"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["STATUS"] = beautifultable.BeautifulTable.ALIGN_LEFT

    running_instances = scan.find_transient_instances(vmstore=args.vmstore)
    for instance in running_instances:
        row = [
            instance.name,
            instance.primary_image,
            "Started {}".format(instance.start_time.strftime("%Y-%m-%d %H:%M:%S")),
        ]

        if args.pid is True:
            row.append(str(instance.transient_pid))
        if args.ssh is True:
            row.append(str(instance.ssh_port is not None))
        table.append_row(row)

    if args.all is True:
        for vm in vmstore.vmstates(lock_timeout=0):
            # All VMs returned from vmstates must be offline because we wouldn't be
            # able to lock/read the vmstate otherwise
            row = [vm.name, vm.primary_image.backend_image_name, "Offline"]
            if args.pid is True:
                row.append("")
            if args.ssh is True:
                row.append(str(configuration.config_requires_ssh(vm.config)))
            table.append_row(row)

    print(table)


def commit_impl(args: argparse.Namespace) -> None:
    imgstore = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=imgstore, path=args.vmstore)

    with vmstore.lock_vmstate_by_name(args.vm, timeout=_COMMIT_CHECK_TIMEOUT) as state:
        imgstore.commit_vmstate(state, args.name)


def image_ls_impl(args: argparse.Namespace) -> None:
    imgstore = store.BackendImageStore(path=args.image_backend)

    table = beautifultable.BeautifulTable(max_width=1000)
    table.column_headers = ["NAME", "VIRT SIZE", "REAL SIZE"]

    table.set_style(beautifultable.BeautifulTable.STYLE_NONE)
    table.column_alignments["NAME"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.column_alignments["VIRT SIZE"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    table.column_alignments["REAL SIZE"] = beautifultable.BeautifulTable.ALIGN_RIGHT

    for image in imgstore.backend_image_list():
        table.append_row(
            [
                image.identifier,
                utils.format_bytes(image.virtual_size),
                utils.format_bytes(image.actual_size),
            ]
        )
    print(table)


def image_build_impl(args: argparse.Namespace) -> None:
    config = configuration.create_transient_build_config(vars(args))
    imgstore = store.BackendImageStore(path=config.image_backend)
    builder = build.ImageBuilder(config, imgstore)
    builder.build()


def image_rm_impl(args: argparse.Namespace) -> None:
    imgstore = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=imgstore, path=args.vmstore)

    for name in args.name:
        images = imgstore.backend_image_list(image_identifier=name)
        if len(images) == 0:
            raise utils.TransientError(msg=f"No image in backend with name '{name}'")
        for item in images:
            vms_using_image = vmstore.backend_image_in_use(item)
            if vms_using_image:
                msg = f"Backend '{item.identifier}' is in use by {vms_using_image}"
                if not args.force:
                    raise utils.TransientError(msg=msg)
                else:
                    logging.warning(msg)

            imgstore.delete_image(item)


def sigint_handler(sig: int, _frame: Any) -> None:
    logging.warning("transient process received SIGINT")
    sys.exit(1)


def __dispatch_command(
    parsed_arguments: argparse.Namespace, qemu_args: List[str]
) -> None:
    command_mappings = {
        "create": (create_impl, True),
        "run": (run_impl, True),
        "rm": (rm_impl, False),
        "ssh": (ssh_impl, False),
        "start": (start_impl, True),
        "stop": (stop_impl, False),
        "ps": (ps_impl, False),
        "commit": (commit_impl, False),
        "image": {
            "ls": (image_ls_impl, False),
            "build": (image_build_impl, False),
            "rm": (image_rm_impl, False),
        },
    }

    # Starting with a field named 'root_command', recursively look through the
    # command_mappings object to find the appropriate callback. This is required
    # because some subcommands have the same name as sub-subcommands (e.g., 'rm'
    # and 'image rm'.)
    mapping: Any = command_mappings
    field = "root_command"
    while True:
        name = getattr(parsed_arguments, field)
        value = mapping[name]
        delattr(parsed_arguments, field)

        if isinstance(value, tuple):
            callback, needs_qemu = value
            break
        else:
            mapping = value
            field = name + "_command"

    if needs_qemu is True:
        # The 'hidden' field should never contain actual values, replace them
        # with what we parsed ourselves
        setattr(parsed_arguments, "qemu_args", qemu_args)

    callback(parsed_arguments)


def main() -> None:
    signal.signal(signal.SIGINT, sigint_handler)

    # Manually split on the '--' to avoid any parsing ambiguity
    if sys.argv.count("--") == 0:
        transient_args = sys.argv[1:]
        qemu_args = []
    else:
        arg_split_idx = sys.argv.index("--")
        transient_args = sys.argv[1:arg_split_idx]
        qemu_args = sys.argv[arg_split_idx + 1 :]

    # Now parse the provided args and call the appropriate callback
    parsed = args.ROOT_PARSER.parse_args(transient_args)

    set_log_level(parsed.verbose)

    # Verbosity is not used after setting the log level, remove it.
    delattr(parsed, "verbose")

    try:
        __dispatch_command(parsed, qemu_args)
    except (
        configuration.ConfigFileOptionError,
        configuration.ConfigFileParsingError,
        configuration.CLIArgumentError,
        FileNotFoundError,
        utils.TransientError,
    ) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
