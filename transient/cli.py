import beautifultable  # type: ignore
import logging
import os
import signal
import sys

from . import args
from . import configuration
from . import build
from . import editor
from . import store
from . import scan
from . import ssh
from . import transient
from . import utils
from . import __version__

from typing import List, Any

_DEFAULT_TIMEOUT = 2.5
_TERMINATE_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
_COMMIT_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
_START_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
_CP_CHECK_TIMEOUT = _DEFAULT_TIMEOUT
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


def create_impl(args: args.TransientArgs) -> None:
    """Create (but do not run) a transient virtual machine"""

    config = configuration.create_transient_create_config(args)
    backend = store.BackendImageStore(path=config.image_backend)
    vmstore = store.VmStore(backend=backend, path=config.vmstore)
    name = vmstore.create_vmstate(config)
    print(f"Created VM '{name}'")


def start_impl(args: args.TransientArgs) -> None:
    """Start an existing virtual machine"""
    config = configuration.create_transient_start_config(args)
    backend = store.BackendImageStore(path=config.image_backend)
    vmstore = store.VmStore(backend=backend, path=config.vmstore)

    with vmstore.lock_vmstate_by_name(config.name, _START_CHECK_TIMEOUT) as state:
        run_config = configuration.run_config_from_create_and_start(state.config, config)

    trans = transient.TransientVm(config=run_config, vmstore=vmstore)
    trans.run()


def run_impl(args: args.TransientArgs) -> None:
    """Run a transient virtual machine."""
    config = configuration.create_transient_run_config(args)

    backend = store.BackendImageStore(path=config.image_backend)
    vmstore = store.VmStore(backend=backend, path=config.vmstore)

    trans = transient.TransientVm(config=config, vmstore=vmstore)
    trans.run()


def rm_impl(args: args.TransientArgs) -> None:
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


def stop_impl(args: args.TransientArgs) -> None:
    backend = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=backend, path=args.vmstore)

    for name in args.name:
        __terminate_vm(name, vmstore, args.kill is True, verify=False)


def ssh_impl(args: args.TransientArgs) -> None:
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


def ps_impl(args: args.TransientArgs) -> None:
    backend = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=backend, path=args.vmstore)

    # Arbitrary max width to avoid line breaks
    table = beautifultable.BeautifulTable(maxwidth=1000)
    headers = ["NAME", "IMAGE", "STATUS"]

    if args.pid is True:
        headers.append("PID")
    if args.ssh is True:
        headers.append("SSH")

    table.columns.header = headers

    if args.pid is True:
        table.columns.alignment["PID"] = beautifultable.BeautifulTable.ALIGN_RIGHT
    if args.ssh is True:
        table.columns.alignment["SSH"] = beautifultable.BeautifulTable.ALIGN_RIGHT

    table.set_style(beautifultable.BeautifulTable.STYLE_NONE)
    table.columns.alignment["NAME"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.columns.alignment["IMAGE"] = beautifultable.BeautifulTable.ALIGN_LEFT
    table.columns.alignment["STATUS"] = beautifultable.BeautifulTable.ALIGN_LEFT

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
        table.rows.append(row)

    if args.all is True:
        for vm in vmstore.vmstates(lock_timeout=0):
            # All VMs returned from vmstates must be offline because we wouldn't be
            # able to lock/read the vmstate otherwise
            row = [vm.name, vm.primary_image.backend_image_name, "Offline"]
            if args.pid is True:
                row.append("")
            if args.ssh is True:
                row.append(str(configuration.config_requires_ssh(vm.config)))
            table.rows.append(row)

    print(table)


def commit_impl(args: args.TransientArgs) -> None:
    imgstore = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=imgstore, path=args.vmstore)

    with vmstore.lock_vmstate_by_name(args.vm, timeout=_COMMIT_CHECK_TIMEOUT) as state:
        imgstore.commit_vmstate(state, args.name)


def cp_impl(args: args.TransientArgs) -> None:
    imgstore = store.BackendImageStore(path=args.image_backend)
    vmstore = store.VmStore(backend=imgstore, path=args.vmstore)

    if len(args.path) < 2:
        raise utils.TransientError(msg="Missing destination argument")
    elif ":" not in args.path[-1] and not all(":" in p for p in args.path[:-1]):
        raise utils.TransientError(
            msg="If destination is not a VM path, all source paths must be VM paths"
        )
    elif ":" in args.path[-1] and any(":" in p for p in args.path[:-1]):
        raise utils.TransientError(
            msg="If destination is a VM path, all source paths must not be VM paths"
        )

    copy_config = {}
    if ":" in args.path[-1]:
        vm_name, destination = args.path[-1].split(":")
        copy_to_vm = True
        copy_config[vm_name] = args.path[:-1]
    else:
        destination = args.path[-1]
        copy_to_vm = False
        for source in args.path[:-1]:
            vm_name, path = source.split(":")
            if vm_name not in copy_config:
                copy_config[vm_name] = [path]
            else:
                copy_config[vm_name].append(path)

    for vm_name, cfg in copy_config.items():
        with vmstore.lock_vmstate_by_name(vm_name, timeout=_CP_CHECK_TIMEOUT) as state:
            with editor.ImageEditor(
                state.primary_image.path, args.ssh_timeout, args.qmp_timeout, args.rsync
            ) as image_editor:
                for source in cfg:
                    if copy_to_vm is True:
                        image_editor.copy_in(source, destination)
                    else:
                        image_editor.copy_out(source, destination)


def image_ls_impl(args: args.TransientArgs) -> None:
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


def image_build_impl(args: args.TransientArgs) -> None:
    config = configuration.create_transient_build_config(args)
    imgstore = store.BackendImageStore(path=config.image_backend)
    builder = build.ImageBuilder(config, imgstore)
    builder.build()


def image_rm_impl(args: args.TransientArgs) -> None:
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


CLI_COMMAND_MAPPINGS = {
    "create": (create_impl, True),
    "run": (run_impl, True),
    "rm": (rm_impl, False),
    "ssh": (ssh_impl, False),
    "start": (start_impl, True),
    "stop": (stop_impl, False),
    "ps": (ps_impl, False),
    "commit": (commit_impl, False),
    "cp": (cp_impl, False),
    "image": {
        "ls": (image_ls_impl, False),
        "build": (image_build_impl, False),
        "rm": (image_rm_impl, False),
    },
}


def __dispatch_command(transient_args: List[str], qemu_args: List[str]) -> None:

    parsed_arguments = args.TransientArgs(transient_args, qemu_args, CLI_COMMAND_MAPPINGS)
    set_log_level(parsed_arguments.verbosity)
    parsed_arguments.callback(parsed_arguments)


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

    try:
        __dispatch_command(transient_args, qemu_args)
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
