import click
import logging
import signal
import sys

from . import configuration
from . import build
from . import image
from . import transient
from . import utils
from . import __version__

from typing import List, Any, Optional, Union, Callable, Iterable


def _get_version(
    ctx: click.Context, param: Union[click.Option, click.Parameter], value: Any
) -> None:
    if not value:
        return
    click.echo(f"transient {__version__}", color=ctx.color)
    ctx.exit()


_common_options = [
    click.option(
        "-image-frontend", type=str, help="The location to place per-vm disk images",
    ),
    click.option(
        "-image-backend",
        type=str,
        help="The location to place the shared, read-only backing disk images",
    ),
    click.option(
        "-image",
        multiple=True,
        type=str,
        help="Disk image to use (this option can be repeated)",
    ),
]


def with_common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    for option in reversed(_common_options):
        func = option(func)
    return func


class TransientRunCommand(click.Command):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(ctx.command_path, "[OPTIONS] -- [QEMU_ARGS]...")

    # Override the normal Command parser to use the Transient one
    def make_parser(self, ctx: click.Context) -> click.parser.OptionParser:
        parser = TransientOptionParser(ctx)
        for param in self.get_params(ctx):
            param.add_to_parser(parser, ctx)
        return parser


class TransientOptionParser(click.parser.OptionParser):
    # This class is identical to the standard Click OptionParser, except that it
    # interprets _every_ argument as a longopt. This prevents the parser from
    # getting confused on things like '-ssh-foobar' and parsing it as '-s sh-foobar'
    # (which later fails because 'sh-foobar' is passed as a shared folder spec)
    def add_option(
        self,
        opts: Iterable[str],
        dest: str,
        action: Optional[str] = None,
        nargs: int = 1,
        const: Optional[bool] = None,
        obj: Optional[click.Option] = None,
    ) -> None:
        super().add_option(opts, dest, action, nargs, const, obj)

        # Move every short opt in to the long opts
        self._long_opt.update(self._short_opt)
        self._short_opt = {}

    def _process_opts(self, arg: str, state: click.parser.ParsingState) -> None:
        explicit_value = None
        if "=" in arg:
            long_opt, explicit_value = arg.split("=", 1)
        else:
            long_opt = arg
        assert self.ctx is not None
        norm_long_opt = click.parser.normalize_opt(long_opt, self.ctx)

        self._match_long_opt(norm_long_opt, explicit_value, state)  # type: ignore


@click.group()
@click.help_option("-h", "--help")
@click.option("-v", "--verbose", count=True)
@click.option(
    "--version",
    help="Show the transient version",
    expose_value=False,
    callback=_get_version,
    is_flag=True,
    is_eager=True,
)
def cli_entry(verbose: int) -> None:
    log_level = logging.ERROR
    if verbose == 1:
        log_level = logging.WARNING
    elif verbose == 2:
        log_level = logging.INFO
    elif verbose >= 3:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s:%(levelname)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.help_option("-h", "--help")
@with_common_options
@click.option(
    "-copy-in-before",
    "-b",
    multiple=True,
    type=str,
    help="Copy a file or directory into the VM before running "
    + "(path/on/host:/absolute/path/on/guest)",
)
@click.option(
    "-copy-out-after",
    "-a",
    multiple=True,
    type=str,
    help="Copy a file or directory out of the VM after running "
    + "(/absolute/path/on/VM:path/on/host)",
)
@click.option("-name", type=str, help="Create a vm with the given name")
@click.option(
    "-ssh-console",
    "-ssh",
    is_flag=True,
    help="Use an ssh connection instead of the serial console",
)
@click.option(
    "-ssh-with-serial",
    "-sshs",
    is_flag=True,
    help="Show the serial output before SSH connects (implies -ssh)",
)
@click.option("-ssh-user", "-u", type=str, help="User to pass to SSH")
@click.option("-ssh-bin-name", type=str, help="SSH binary to use")
@click.option(
    "-ssh-timeout", type=int, help="Time to wait for SSH connection before failing",
)
@click.option(
    "-ssh-port", type=int, help="Host port the guest port 22 is connected to",
)
@click.option(
    "-ssh-command", "-cmd", type=str, help="Run an ssh command instead of a console",
)
@click.option(
    "-ssh-net-driver",
    type=str,
    help="The QEMU virtual network device driver e.g. e1000, rtl8139, virtio-net-pci (default)",
)
@click.option(
    "-shutdown-timeout",
    type=int,
    help="The time to wait for shutdown before terminating QEMU",
)
@click.option(
    "-qmp-timeout",
    type=int,
    help="The time in seconds to wait for the QEMU QMP connection to be established",
)
@click.option(
    "-copy-timeout",
    type=int,
    help="The maximum time to wait for a copy-in-before or copy-out-after operation to complete",
)
@click.option(
    "-shared-folder",
    "-s",
    multiple=True,
    type=str,
    help="Share a host directory with the guest (/path/on/host:/path/on/guest)",
)
@click.option(
    "-prepare-only",
    is_flag=True,
    help="Only download/create vm disks. Do not start the vm",
)
@click.option("-config", "-c", nargs=1, help="Use a configuration file")
@click.argument("QEMU_ARGS", nargs=-1)
@cli_entry.command(name="run", cls=TransientRunCommand)
def run_impl(**kwargs: Any) -> None:
    """Run a transient virtual machine.

    QEMU_ARGS will be passed directly to QEMU.
    """
    try:
        config = configuration.create_transient_run_config(kwargs)
    except (
        configuration.ConfigFileOptionError,
        configuration.ConfigFileParsingError,
        configuration.CLIArgumentError,
        FileNotFoundError,
    ) as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    store = image.ImageStore(
        backend_dir=config.image_backend, frontend_dir=config.image_frontend
    )
    trans = transient.TransientVm(config=config, store=store)

    try:
        trans.run()
        sys.exit(0)
    except utils.TransientProcessError as e:
        print(e, file=sys.stderr)
        sys.exit(e.returncode)


@click.help_option("-h", "--help")
@with_common_options
@click.option("-force", "-f", help="Do not prompt before deletion", is_flag=True)
@click.option(
    "-name", type=str, help="Delete images associated with the given vm name",
)
@cli_entry.command("delete")
def delete_impl(**kwargs: Any) -> None:
    """Delete transient disks"""
    try:
        config = configuration.create_transient_delete_config(kwargs)
    except configuration.CLIArgumentError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    store = image.ImageStore(
        backend_dir=config.image_backend, frontend_dir=config.image_frontend
    )
    images = _find_requested_images(store, config)

    if len(images) == 0:
        print("No images match selection", file=sys.stderr)
        sys.exit(1)

    print("The following images will be deleted:\n")
    frontend, backend = image.format_image_table(images)
    if len(frontend) > 0:
        print("Frontend Images:")
        print(frontend)
    if len(backend) > 0:
        print("\nBackend Images:")
        print(backend)

    if config.force is False:
        response = utils.prompt_yes_no("Proceed?", default=False)
    else:
        response = True

    if response is False:
        sys.exit(0)

    for image_info in images:
        logging.info(f"Deleting image at {image_info.path}")
        store.delete_image(image_info)
    sys.exit(0)


@click.help_option("-h", "--help")
@with_common_options
@click.option(
    "-name", type=str, help="List disks associated with the given vm name",
)
@cli_entry.command("list")
def list_impl(**kwargs: Any) -> None:
    """List transient disk information"""
    try:
        config = configuration.create_transient_list_config(kwargs)
    except configuration.CLIArgumentError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    store = image.ImageStore(
        backend_dir=config.image_backend, frontend_dir=config.image_frontend
    )
    images = _find_requested_images(store, config)

    if len(images) == 0:
        print("No images match selection", file=sys.stderr)
        sys.exit(1)

    frontend, backend = image.format_image_table(images)
    if len(frontend) > 0:
        print("Frontend Images:")
        print(frontend)
    if len(backend) > 0:
        print("\nBackend Images:")
        print(backend)
    sys.exit(0)


@click.help_option("-h", "--help")
@click.option("-file", "-f", type=str, help="Specify a path to the Imagefile")
@click.option(
    "-image-backend",
    type=str,
    help="The location to place the shared, read-only backing disk images",
)
@click.option(
    "-ssh-timeout", type=int, help="Time to wait for SSH connection before failing"
)
@click.option(
    "-qmp-timeout",
    type=int,
    help="The time in seconds to wait for the QEMU QMP connection to be established",
)
@click.option(
    "-local", is_flag=True, help="Produce image in the build-dir instead of the backend",
)
@click.option("-name", help="The name given to the new image", required=True)
@click.argument("build-dir")
@cli_entry.command("build")
def build_impl(**kwargs: Any) -> None:
    """List transient disk information"""
    try:
        config = configuration.create_transient_build_config(kwargs)
    except configuration.CLIArgumentError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    store = image.ImageStore(backend_dir=config.image_backend, frontend_dir=None)
    builder = build.ImageBuilder(config, store)
    builder.build()
    sys.exit(0)


def _find_requested_images(
    store: image.ImageStore, config: configuration.Config
) -> List[image.BaseImageInfo]:
    images: List[image.BaseImageInfo] = []
    if config.name is not None:
        if len(config.image) == 0:
            images = list(store.frontend_image_list(config.name))
        else:
            for image_identifier in config.image:
                images.extend(store.frontend_image_list(config.name, image_identifier))
    else:
        if len(config.image) == 0:
            images = list(store.backend_image_list())
            images.extend(store.frontend_image_list())
        else:
            for image_identifier in config.image:
                images.extend(store.backend_image_list(image_identifier))
                images.extend(
                    store.frontend_image_list(image_identifier=image_identifier)
                )
    return images


def sigint_handler(sig: int, frame: Any) -> None:
    logging.warning("transient process received SIGINT")
    sys.exit(1)


def main() -> None:
    signal.signal(signal.SIGINT, sigint_handler)

    # Click aggressively insists on having locales prior to python 3.7.
    # This won't be the case inside docker, for example, so skip the
    # check.
    click.core._verify_python3_env = lambda: None  # type: ignore
    cli_entry()
