import argparse

from . import utils
from . import qemu
from . import __version__

from typing import Any, Tuple, Optional


class TransientArgumentDefaultsHelpFormatter(argparse.HelpFormatter):
    def _get_help_string(self, action: argparse.Action) -> Optional[str]:
        help = action.help
        if help is not None and "%(default)" not in help:
            if action.default not in (argparse.SUPPRESS, None, []):
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help += " [default: %(default)s]"
        return help


def define_common_parser(include_defaults: bool) -> Tuple[argparse.ArgumentParser, ...]:
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
        default=set_default(90),
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
        default=[],
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
        default=[],
        help="Share a host directory with the guest (/path/on/host:/path/on/guest)",
    )

    # Common arguments for single runs of a vm (e.g., start/run but not create)
    common_oneshot_parser = argparse.ArgumentParser(add_help=False)
    common_oneshot_parser.add_argument(
        "--copy-in-before",
        "-b",
        type=str,
        action="append",
        default=[],
        help="Copy a file or directory into the VM before running "
        + "(path/on/host:/absolute/path/on/guest)",
    )
    common_oneshot_parser.add_argument(
        "--copy-out-after",
        "-a",
        type=str,
        action="append",
        default=[],
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
        default=[],
        help="Add an extra disk image to the VM",
    )

    return (
        common_parser,
        common_ssh_parser,
        common_run_parser,
        common_oneshot_parser,
        common_create_parser,
    )


(
    _COMMON_PARSER,
    _COMMON_SSH_PARSER,
    _COMMON_RUN_PARSER,
    _COMMON_ONESHOT_PARSER,
    _COMMON_CREATE_PARSER,
) = define_common_parser(include_defaults=True)

(
    _COMMON_PARSER_NO_DEFAULTS,
    _COMMON_SSH_PARSER_NO_DEFAULTS,
    _COMMON_RUN_PARSER_NO_DEFAULTS,
    _COMMON_ONESHOT_PARSER_NO_DEFAULTS,
    _COMMON_CREATE_PARSER_NO_DEFAULTS,
) = define_common_parser(include_defaults=False)


ROOT_PARSER = argparse.ArgumentParser(
    prog="transient", parents=[], formatter_class=TransientArgumentDefaultsHelpFormatter
)
ROOT_PARSER.add_argument(
    "--version", action="version", version=f"{ROOT_PARSER.prog} {__version__}"
)
ROOT_PARSER.add_argument(
    "--verbose", "-v", action="count", default=0, help="Verbosity level for logging"
)
_SUBPARSERS = ROOT_PARSER.add_subparsers(dest="root_command")


# Define 'create' subcommand
CREATE_PARSER = _SUBPARSERS.add_parser(
    "create",
    parents=[_COMMON_RUN_PARSER, _COMMON_CREATE_PARSER],
    help="Create (but do not start) a new VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
CREATE_PARSER.add_argument("primary_image", help="Disk image to boot", type=str)
CREATE_PARSER.add_argument("--name", help="Virtual machine name", type=str)
CREATE_PARSER.add_argument("--qemu_args", help=argparse.SUPPRESS, nargs="*", type=str)


# Define 'run' subcommand
RUN_PARSER = _SUBPARSERS.add_parser(
    "run",
    parents=[_COMMON_RUN_PARSER, _COMMON_ONESHOT_PARSER, _COMMON_CREATE_PARSER],
    help="Create and run a VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
RUN_PARSER.add_argument("primary_image", help="Disk image to boot", type=str)
RUN_PARSER.add_argument("--name", help="Virtual machine name", type=str)
RUN_PARSER.add_argument("--qemu_args", help=argparse.SUPPRESS, nargs="*", type=str)


# Define 'start' subcommand
# This subcommand must _not_ have any defaults, as we will combine the user provided
# values with the ones used during 'create' and we must be able to distinguish between
# a user-supplied value that happens to be the default, and a value not supplied
# by the user.
START_PARSER = _SUBPARSERS.add_parser(
    "start",
    parents=[_COMMON_RUN_PARSER_NO_DEFAULTS, _COMMON_ONESHOT_PARSER_NO_DEFAULTS],
    help="Start a previously created VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
START_PARSER.add_argument("name", help="Virtual machine name", type=str)
START_PARSER.add_argument("--qemu_args", help=argparse.SUPPRESS, nargs="*", type=str)


# Define 'rm' subcommand
RM_PARSER = _SUBPARSERS.add_parser(
    "rm",
    parents=[_COMMON_PARSER],
    help="Remove a created VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
RM_PARSER.add_argument(
    "--force",
    "-f",
    help="Force removal. Will stop the VM if currently running",
    action="store_const",
    const=True,
)
RM_PARSER.add_argument("name", help="Virtual machine name", nargs="+")


# Define 'stop' subcommand
STOP_PARSER = _SUBPARSERS.add_parser(
    "stop",
    parents=[_COMMON_PARSER],
    help="Stop a running VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
STOP_PARSER.add_argument(
    "--kill",
    "-k",
    help="Send SIGKILL instead of SIGTERM",
    action="store_const",
    const=True,
)
STOP_PARSER.add_argument("name", help="Virtual machine name", nargs="+")


# Define 'ssh' subcommand
SSH_PARSER = _SUBPARSERS.add_parser(
    "ssh",
    parents=[_COMMON_PARSER, _COMMON_SSH_PARSER],
    help="SSH to a running VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
SSH_PARSER.add_argument(
    "--wait",
    "-w",
    action="store_const",
    const=True,
    help="Wait for at most 'ssh-timeout' for a vm with the given name to exist",
)
SSH_PARSER.add_argument("name", help="Virtual machine name")


# Define 'ps' subcommand
PS_PARSER = _SUBPARSERS.add_parser(
    "ps",
    parents=[_COMMON_PARSER],
    help="Print information about VMs",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
PS_PARSER.add_argument(
    "-a",
    "--all",
    action="store_const",
    const=True,
    help="Show all VMs, default is show only running VMs",
)
PS_PARSER.add_argument(
    "--ssh", action="store_const", const=True, help="Print whether VMs have SSH support"
)
PS_PARSER.add_argument(
    "--pid", action="store_const", const=True, help="Print running VMs PID"
)


COMMIT_PARSER = _SUBPARSERS.add_parser(
    "commit",
    parents=[_COMMON_PARSER],
    help="Create a new disk image from the state of a current VM",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
COMMIT_PARSER.add_argument(
    "vm", help="VM to use as the source of the new image", type=str
)
COMMIT_PARSER.add_argument("name", help="Name of the new image", type=str)


# Define 'image' subcommands
IMAGE_PARSER = _SUBPARSERS.add_parser(
    "image",
    parents=[],
    help="Print information about images",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
_IMAGE_SUBPARSERS = IMAGE_PARSER.add_subparsers(dest="image_command")
_IMAGE_SUBPARSERS.required = True

# Define 'image ls' subcommand
IMAGE_LS_PARSER = _IMAGE_SUBPARSERS.add_parser(
    "ls",
    parents=[_COMMON_PARSER],
    help="Print information about images",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)

# Define 'image build' subcommand
IMAGE_BUILD_PARSER = _IMAGE_SUBPARSERS.add_parser(
    "build",
    parents=[_COMMON_PARSER],
    help="Build a new image",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
IMAGE_BUILD_PARSER.add_argument(
    "build_dir", metavar="build-dir", help="Directory use as root of build", type=str
)
IMAGE_BUILD_PARSER.add_argument(
    "--file", "-f", help="Specify a path to the Imagefile", type=str
)
IMAGE_BUILD_PARSER.add_argument("--name", help="Name of new disk", type=str)
IMAGE_BUILD_PARSER.add_argument(
    "--qmp-timeout",
    type=int,
    default=qemu.QMP_DEFAULT_TIMEOUT,
    help="The time in seconds to wait for the QEMU QMP connection to be established",
)
IMAGE_BUILD_PARSER.add_argument(
    "--ssh-timeout",
    type=int,
    default=90,
    help="Time to wait for SSH connection before failing",
)
IMAGE_BUILD_PARSER.add_argument(
    "--local",
    action="store_const",
    const=True,
    help="Produce image in the build-dir instead of the backend",
)

# Define 'image rm' subcommand
IMAGE_RM_PARSER = _IMAGE_SUBPARSERS.add_parser(
    "rm",
    parents=[_COMMON_PARSER],
    help="Remove an image from the backend",
    formatter_class=TransientArgumentDefaultsHelpFormatter,
)
IMAGE_RM_PARSER.add_argument("name", help="Image name", nargs="+")
IMAGE_RM_PARSER.add_argument(
    "--force",
    "-f",
    help="Force removal even if image is required by a VM",
    action="store_const",
    const=True,
)
