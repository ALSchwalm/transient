import argparse

from . import ssh
from . import utils
from . import qemu
from . import __version__

from typing import Any, Tuple, Optional, List, Iterator, Dict, Callable


class TransientArgumentDefaultsHelpFormatter(argparse.HelpFormatter):
    def _get_help_string(self, action: argparse.Action) -> Optional[str]:
        help = action.help
        if help is not None and "%(default)" not in help:
            if action.default not in (argparse.SUPPRESS, None, []):
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help += " [default: %(default)s]"
        return help

    def _fill_text(self, text: str, _width: Any, indent: str) -> str:
        return "".join(indent + line for line in text.splitlines(keepends=True))


def define_parsers(include_defaults: bool) -> Tuple[argparse.ArgumentParser, ...]:
    def set_default(value: Any) -> Any:
        if include_defaults is True:
            return value
        else:
            return None

    # Common arguments used for all subcommands
    common_parser = argparse.ArgumentParser(add_help=False)

    # Use 'SUPPRESS' here so subcommand parser values won't override flags passed
    # earlier in the command line
    common_parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=argparse.SUPPRESS,
        help="Verbosity level for logging",
    )
    common_parser.add_argument(
        "--vmstore",
        type=str,
        default=set_default(utils.default_vmstore_dir()),
        help="Location to place VM images and configuration files",
    )
    common_parser.add_argument(
        "--image-backend",
        type=str,
        default=set_default(utils.default_backend_dir()),
        help="Location to place the shared, read-only backing disk images",
    )

    # Common arguments for commands that use SSH in some way
    common_ssh_parser = argparse.ArgumentParser(add_help=False)
    common_ssh_parser.add_argument(
        "--ssh-user", type=str, help="User to pass to SSH", default=set_default("vagrant")
    )
    common_ssh_parser.add_argument(
        "--ssh-bin-name", type=str, help="SSH binary to use", default=set_default("ssh")
    )
    common_ssh_parser.add_argument(
        "--ssh-timeout",
        type=int,
        default=set_default(ssh.SSH_DEFAULT_TOTAL_TIMEOUT),
        help="Time to wait for SSH connection before failing",
    )
    common_ssh_parser.add_argument(
        "--ssh-command", "--cmd", type=str, help="Run an ssh command instead of a console"
    )
    common_ssh_parser.add_argument(
        "--ssh-option",
        "-o",
        type=str,
        action="append",
        help="Pass an option to SSH",
        default=set_default([]),
    )

    # Common arguments for all vm running features (e.g., create/start/run)
    common_run_parser = argparse.ArgumentParser(
        add_help=False, parents=[common_ssh_parser, common_parser]
    )
    common_run_parser.add_argument(
        "--ssh-console",
        "--ssh",
        action="store_const",
        const=True,
        help="Use an ssh connection instead of the serial console",
    )
    common_run_parser.add_argument(
        "--ssh-with-serial",
        "--sshs",
        action="store_const",
        const=True,
        help="Show the serial output before SSH connects (implies --ssh)",
    )
    common_run_parser.add_argument(
        "--sftp-bin-name",
        type=str,
        help="SFTP server binary to use",
        default=set_default("sftp-server"),
    )
    common_run_parser.add_argument(
        "--ssh-port", type=int, help="Host port the guest port 22 is connected to"
    )
    common_run_parser.add_argument(
        "--ssh-net-driver",
        type=str,
        help="The QEMU virtual network device driver e.g. e1000, rtl8139, virtio-net-pci",
        default=set_default("virtio-net-pci"),
    )
    common_run_parser.add_argument(
        "--no-virtio-scsi",
        action="store_const",
        const=True,
        help="Use the QEMU default drive interface (ide) instead of virtio-pci-scsi",
    )
    common_run_parser.add_argument(
        "--shutdown-timeout",
        type=int,
        default=set_default(20),
        help="The time in seconds to wait for shutdown before terminating QEMU",
    )
    common_run_parser.add_argument(
        "--qemu-bin-name",
        type=str,
        help="QEMU binary to use",
        default=set_default("qemu-system-x86_64"),
    )
    common_run_parser.add_argument(
        "--qmp-timeout",
        type=int,
        default=set_default(qemu.QMP_DEFAULT_TIMEOUT),
        help="The time in seconds to wait for the QEMU QMP connection to be established",
    )
    common_run_parser.add_argument(
        "--shared-folder",
        "-s",
        action="append",
        type=str,
        default=set_default([]),
        help="Share a host directory with the guest (/path/on/host:/path/on/guest)",
    )
    common_run_parser.add_argument(
        "--config", type=str, help="Path to a config toml file to read parameters from"
    )

    # Common arguments for single runs of a vm (e.g., start/run but not create)
    common_oneshot_parser = argparse.ArgumentParser(add_help=False)
    common_oneshot_parser.add_argument(
        "--copy-in-before",
        "-b",
        type=str,
        action="append",
        default=set_default([]),
        help="Copy a file or directory into the VM before running "
        + "(path/on/host:/absolute/path/on/guest)",
    )
    common_oneshot_parser.add_argument(
        "--copy-out-after",
        "-a",
        type=str,
        action="append",
        default=set_default([]),
        help="Copy a file or directory out of the VM after running "
        + "(/absolute/path/on/VM:path/on/host)",
    )
    common_oneshot_parser.add_argument(
        "--copy-timeout",
        type=int,
        help="The maximum time to wait for a copy-in-before or copy-out-after operation to complete",
    )
    common_oneshot_parser.add_argument(
        "--rsync",
        action="store_const",
        const=True,
        help="Use rsync for copy-in-before/copy-out-after operations",
    )

    # Common arguments for creation of a vm (e.g., create/run but not start)
    common_create_parser = argparse.ArgumentParser(add_help=False)
    common_create_parser.add_argument(
        "--extra-image",
        action="append",
        type=str,
        default=set_default([]),
        help="Add an extra disk image to the VM",
    )

    root_parser = argparse.ArgumentParser(
        prog="transient",
        parents=[],
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    root_parser.add_argument(
        "--version", action="version", version=f"{root_parser.prog} {__version__}"
    )
    root_parser.add_argument(
        "--verbose", "-v", action="count", default=0, help="Verbosity level for logging"
    )
    subparsers = root_parser.add_subparsers(dest="root_command")

    # Define 'create' subcommand
    create_parser = subparsers.add_parser(
        "create",
        parents=[common_run_parser, common_create_parser],
        help="Create (but do not start) a new VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    create_parser.add_argument("image", help="Disk image to boot", type=str)
    create_parser.add_argument("--name", help="Virtual machine name", type=str)
    create_parser.add_argument("--qemu_args", help=argparse.SUPPRESS, nargs="*", type=str)

    # Define 'run' subcommand
    run_parser = subparsers.add_parser(
        "run",
        parents=[common_run_parser, common_oneshot_parser, common_create_parser],
        help="Create and run a VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    run_parser.add_argument("image", help="Disk image to boot", type=str)
    run_parser.add_argument("--name", help="Virtual machine name", type=str)
    run_parser.add_argument("--qemu_args", help=argparse.SUPPRESS, nargs="*", type=str)

    # Define 'start' subcommand
    # This subcommand must _not_ have any defaults, as we will combine the user provided
    # values with the ones used during 'create' and we must be able to distinguish between
    # a user-supplied value that happens to be the default, and a value not supplied
    # by the user.
    start_parser = subparsers.add_parser(
        "start",
        parents=[common_run_parser, common_oneshot_parser],
        help="Start a previously created VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    start_parser.add_argument("name", help="Virtual machine name", type=str)
    start_parser.add_argument("--qemu_args", help=argparse.SUPPRESS, nargs="*", type=str)

    # Define 'rm' subcommand
    rm_parser = subparsers.add_parser(
        "rm",
        parents=[common_parser],
        help="Remove a created VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    rm_parser.add_argument(
        "--force",
        "-f",
        help="Force removal. Will stop the VM if currently running",
        action="store_const",
        const=True,
    )
    rm_parser.add_argument("name", help="Virtual machine name", nargs="+")

    # Define 'stop' subcommand
    stop_parser = subparsers.add_parser(
        "stop",
        parents=[common_parser],
        help="Stop a running VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    stop_parser.add_argument(
        "--kill",
        "-k",
        help="Send SIGKILL instead of SIGTERM",
        action="store_const",
        const=True,
    )
    stop_parser.add_argument("name", help="Virtual machine name", nargs="+")

    # Define 'ssh' subcommand
    ssh_parser = subparsers.add_parser(
        "ssh",
        parents=[common_parser, common_ssh_parser],
        help="SSH to a running VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    ssh_parser.add_argument(
        "--wait",
        "-w",
        action="store_const",
        const=True,
        help="Wait for at most 'ssh-timeout' for a vm with the given name to exist",
    )
    ssh_parser.add_argument("name", help="Virtual machine name")

    # Define 'ps' subcommand
    ps_parser = subparsers.add_parser(
        "ps",
        parents=[common_parser],
        help="Print information about VMs",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    ps_parser.add_argument(
        "-a",
        "--all",
        action="store_const",
        const=True,
        help="Show all VMs, default is show only running VMs",
    )
    ps_parser.add_argument(
        "--ssh",
        action="store_const",
        const=True,
        help="Print whether VMs have SSH support",
    )
    ps_parser.add_argument(
        "--pid", action="store_const", const=True, help="Print running VMs PID"
    )

    commit_parser = subparsers.add_parser(
        "commit",
        parents=[common_parser],
        help="Create a new disk image from the state of a current VM",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    commit_parser.add_argument(
        "vm", help="VM to use as the source of the new image", type=str
    )
    commit_parser.add_argument("name", help="Name of the new image", type=str)

    # Define 'image' subcommands
    image_parser = subparsers.add_parser(
        "image",
        parents=[],
        help="Print information about images",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    image_subparsers = image_parser.add_subparsers(dest="image_command")
    image_subparsers.required = True

    # Define 'image ls' subcommand
    image_ls_parser = image_subparsers.add_parser(
        "ls",
        parents=[common_parser],
        help="Print information about images",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )

    # Define 'image build' subcommand
    image_build_parser = image_subparsers.add_parser(
        "build",
        parents=[common_parser],
        help="Build a new image",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    image_build_parser.add_argument(
        "build_dir", metavar="build-dir", help="Directory use as root of build", type=str
    )
    image_build_parser.add_argument(
        "--file", "-f", help="Specify a path to the Imagefile", type=str
    )
    image_build_parser.add_argument("--name", help="Name of new disk", type=str)
    image_build_parser.add_argument(
        "--qmp-timeout",
        type=int,
        default=set_default(qemu.QMP_DEFAULT_TIMEOUT),
        help="The time in seconds to wait for the QEMU QMP connection to be established",
    )
    image_build_parser.add_argument(
        "--ssh-timeout",
        type=int,
        default=set_default(ssh.SSH_DEFAULT_TOTAL_TIMEOUT),
        help="Time to wait for SSH connection before failing",
    )
    image_build_parser.add_argument(
        "--local",
        action="store_const",
        const=True,
        help="Produce image in the build-dir instead of the backend",
    )

    # Define 'image rm' subcommand
    image_rm_parser = image_subparsers.add_parser(
        "rm",
        parents=[common_parser],
        help="Remove an image from the backend",
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    image_rm_parser.add_argument("name", help="Image name", nargs="+")
    image_rm_parser.add_argument(
        "--force",
        "-f",
        help="Force removal even if image is required by a VM",
        action="store_const",
        const=True,
    )

    # Define 'cp' subcommand
    cp_parser = subparsers.add_parser(
        "cp",
        parents=[common_parser],
        description="""
    Copy files to/from an offline VM. The VM name must be specified
    before the path portion of either the destination or source. For
    example:

        transient cp MY_VM_NAME:/etc/fstab /local/path/fstab

    This command would copy the 'fstab' file from MY_VM_NAME to the
    given local path. A similar command can be used to copy (multiple)
    files from the host machine to the VM disk:

        transient cp file1 file2 MY_VM_NAME:/tmp

    """,
        formatter_class=TransientArgumentDefaultsHelpFormatter,
    )
    cp_parser.add_argument("path", nargs="+", help="The path to copy to/from")
    cp_parser.add_argument(
        "--qmp-timeout",
        type=int,
        default=set_default(qemu.QMP_DEFAULT_TIMEOUT),
        help=argparse.SUPPRESS,
    )
    cp_parser.add_argument(
        "--ssh-timeout",
        type=int,
        default=set_default(ssh.SSH_DEFAULT_TOTAL_TIMEOUT),
        help=argparse.SUPPRESS,
    )
    cp_parser.add_argument(
        "--rsync",
        action="store_const",
        const=True,
        help="Use rsync for copy operations (instead of SCP)",
    )

    return (root_parser, run_parser, create_parser, start_parser, image_build_parser)


(
    ROOT_PARSER,
    RUN_PARSER,
    CREATE_PARSER,
    START_PARSER,
    IMAGE_BUILD_PARSER,
) = define_parsers(include_defaults=True)

(
    ROOT_PARSER_NO_DEFAULTS,
    RUN_PARSER_NO_DEFAULTS,
    CREATE_PARSER_NO_DEFAULTS,
    START_PARSER_NO_DEFAULTS,
    IMAGE_BUILD_PARSER_NO_DEFAULTS,
) = define_parsers(include_defaults=False)


class TransientArgs:
    transient_args: List[str]
    qemu_args: List[str]
    parsed: argparse.Namespace
    user_supplied: argparse.Namespace
    callback: Any
    verbosity: int

    def __init__(
        self,
        transient_args: List[str],
        qemu_args: List[str],
        command_mappings: Dict[Any, Any],
    ) -> None:

        self.transient_args = transient_args
        self.qemu_args = qemu_args
        self.parsed = ROOT_PARSER.parse_args(self.transient_args)
        self.user_supplied = ROOT_PARSER_NO_DEFAULTS.parse_args(self.transient_args)
        self.verbosity = self.parsed.verbose

        self.__remove_arg("verbose")

        # Starting with a field named 'root_command', recursively look through the
        # command_mappings object to find the appropriate callback. This is required
        # because some subcommands have the same name as sub-subcommands (e.g., 'rm'
        # and 'image rm'.)
        callback = None
        mapping: Any = command_mappings
        field = "root_command"
        while True:
            name = getattr(self.parsed, field)
            value = mapping[name]
            self.__remove_arg(field)

            if isinstance(value, tuple):
                callback, needs_qemu = value
                break
            else:
                mapping = value
                field = name + "_command"

        if needs_qemu is True:
            # The 'hidden' field should never contain actual values, replace them
            # with what we parsed ourselves
            self.__add_arg("qemu_args", qemu_args)

        if callback is None:
            raise utils.TransientError(msg="Unable to locate command callback")
        self.callback = callback

    def __getattr__(self, name: str) -> Any:
        return getattr(self.parsed, name)

    def __remove_arg(self, name: str) -> None:
        delattr(self.parsed, name)
        delattr(self.user_supplied, name)

    def __add_arg(self, name: str, value: Any) -> None:
        setattr(self.parsed, name, value)
        setattr(self.user_supplied, name, value)

    def is_user_set(self, name: str) -> bool:
        if hasattr(self.user_supplied, name):
            return self.user_supplied.name is not None
        return False

    def user_supplied_fields(self) -> Iterator[Tuple[Any, Any]]:
        return iter(vars(self.user_supplied).items())

    def __iter__(self) -> Iterator[Tuple[Any, Any]]:
        return iter(vars(self.parsed).items())
