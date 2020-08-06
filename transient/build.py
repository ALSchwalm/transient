import enum
import os
import lark  # type: ignore
import logging
import json
import pathlib
import re
import shutil
import stat
import subprocess

from . import configuration
from . import editor
from . import qemu
from . import image
from . import utils
from . import ssh
from . import static

from typing import (
    cast,
    Any,
    Sequence,
    Callable,
    List,
    Optional,
    TypeVar,
    Type,
    Tuple,
    Union,
)


IMAGEFILE_GRAMMAR = r"""
start: (instruction | _NEWLINE | COMMENT)+
instruction: run | copy | from | disk | partition | add | inspect
run: "RUN"i run_body _NEWLINE
run_body: RUN_CMD+
RUN_CMD: /[^\\\n]/+

copy: "COPY"i copy_source+ copy_destination _NEWLINE
copy_source: PATH
copy_destination: PATH
PATH: /[^ \t\n\\]/i+

add: "ADD"i add_source+ add_destination _NEWLINE
add_source: PATH
add_destination: PATH

from: "FROM"i FROM_SPEC _NEWLINE
FROM_SPEC: /[^ \t\n\\]/+

disk: "DISK"i DISK_SIZE DISK_UNITS DISK_TYPE _NEWLINE
DISK_SIZE: /\d/i+
DISK_UNITS: /[MG]b/i
DISK_TYPE: "GPT"i | "MBR"i

inspect: "INSPECT"i _NEWLINE

partition: "PARTITION"i PARTITION_NUM partition_size? partition_format? partition_mount? partition_flags? _NEWLINE
PARTITION_NUM: /\d/+
partition_size: "SIZE"i DISK_SIZE DISK_UNITS
partition_mount: "MOUNT"i PATH
partition_format: "FORMAT"i PART_FORMAT partition_options?
partition_flags: "FLAGS"i PART_FLAG ("," PART_FLAG)*
partition_options: "OPTIONS"i PART_STRING
PART_FLAG: "BOOT"i | "EFI"i | "BIOS_GRUB"i
PART_FORMAT: /[^ \t\n\\]/i+
PART_STRING: /".*?"/

COMMENT: /#[^\n]*/

%import common.NEWLINE -> _NEWLINE
%import common.WS_INLINE
%ignore WS_INLINE
%ignore COMMENT
%ignore /\\[\t \f]*\r?\n/   // LINE_CONT
"""
IMAGEFILE_PARSER = lark.Lark(IMAGEFILE_GRAMMAR, parser="lalr").parse


class GuestChrootCommand(editor.GuestCommand):
    def __init__(
        self,
        cmd: str,
        ssh_config: ssh.SshConfig,
        connect_timeout: int,
        run_timeout: Optional[int] = None,
        stdin: utils.FILE_TYPE = subprocess.DEVNULL,
        capture_stdout: bool = False,
        capture_stderr: bool = False,
    ):
        escaped_command = cmd.replace("'", "'\\''")
        chroot_command = (
            f"""unshare --fork --pid chroot /mnt /bin/bash -c '{escaped_command}' """
        )
        super().__init__(
            chroot_command,
            ssh_config,
            connect_timeout,
            run_timeout,
            stdin,
            capture_stdout,
            capture_stderr,
        )


class ImageInstruction:
    def commands(self, builder: "ImageBuilder") -> Sequence[editor.Command]:
        return []


class InspectInstruction(ImageInstruction):
    def __init__(self, _ast: lark.tree.Tree) -> None:
        pass

    def __str__(self) -> str:
        return f"INSPECT"


class RunInstruction(ImageInstruction):
    command: str

    def __init__(self, ast: lark.tree.Tree) -> None:
        self.command = " ".join([c.value for c in ast.children[0].children])

    def commands(self, builder: "ImageBuilder") -> Sequence[editor.Command]:
        return [
            GuestChrootCommand(
                self.command, builder.editor.ssh_config, builder.config.ssh_timeout
            )
        ]

    def __str__(self) -> str:
        return f"RUN {self.command}"


class CopyInstruction(ImageInstruction):
    source: List[str]
    destination: str

    def __init__(self, ast: lark.tree.Tree) -> None:
        self.source = [node.children[0].value for node in ast.find_data("copy_source")]
        self.destination = next(ast.find_data("copy_destination")).children[0].value

    def commands(self, builder: "ImageBuilder") -> Sequence[editor.Command]:
        commands = []

        def _copy_func(host_src: str) -> Callable[[], Tuple[None, None]]:
            def _inner() -> Tuple[None, None]:
                builder.editor.copy_in(host_src, self.destination)
                return None, None

            return _inner

        for src in self.source:
            host_src = os.path.join(builder.config.build_dir, src)
            commands.append(editor.HostCommand(_copy_func(host_src)))
        return commands

    def __str__(self) -> str:
        return "COPY {} {}".format(" ".join(self.source), self.destination)


class AddInstruction(ImageInstruction):
    source: List[str]
    destination: str

    def __init__(self, ast: lark.tree.Tree) -> None:
        self.source = [node.children[0].value for node in ast.find_data("add_source")]
        self.destination = next(ast.find_data("add_destination")).children[0].value

    def __is_compressed(self, name: str) -> bool:
        return name.endswith(".tar.gz") or name.endswith(".tar.xz")

    def commands(self, builder: "ImageBuilder") -> Sequence[editor.Command]:
        commands: List[editor.Command] = []

        def _copy_func(host_src: str) -> Callable[[], Tuple[None, None]]:
            def _inner() -> Tuple[None, None]:
                builder.editor.copy_in(host_src, self.destination)
                return None, None

            return _inner

        effective_destination = utils.join_absolute_paths("/mnt", self.destination)
        for src in self.source:
            host_src = os.path.join(builder.config.build_dir, src)
            if not self.__is_compressed(src):
                commands.append(editor.HostCommand(_copy_func(host_src)))
            else:
                commands.append(
                    editor.GuestCommand(
                        f"bsdtar xfP - --directory={effective_destination}",
                        builder.editor.ssh_config,
                        builder.config.ssh_timeout,
                        stdin=open(host_src, "rb"),
                    )
                )
        return commands

    def __str__(self) -> str:
        return "ADD {} {}".format(" ".join(self.source), self.destination)


class DiskInstruction(ImageInstruction):
    size: int
    units: str
    type: str

    def __init__(self, ast: lark.tree.Tree) -> None:
        self.size = int(ast.children[0].value)
        self.units = ast.children[1].value.upper().replace("B", "")
        self.type = ast.children[2].value.upper()

    def commands(self, builder: "ImageBuilder") -> Sequence[editor.Command]:
        return [
            editor.GuestCommand(
                f"echo label:{self.type} | sfdisk /dev/sda",
                builder.editor.ssh_config,
                builder.config.ssh_timeout,
            )
        ]

    def __str__(self) -> str:
        return f"DISK {self.size}{self.units} {self.type}"


class PartitionInstruction(ImageInstruction):
    size: Optional[int]
    format: Optional[str]
    options: Optional[str]
    mount: Optional[str]
    flags: Optional[List[str]]
    number: int

    def __init__(self, ast: lark.tree.Tree) -> None:
        self.number = int(ast.children[0].value)

        format = next(ast.find_data("partition_format"), None)
        if format is not None:
            self.format = format.children[0].value.lower()
            if self.format not in self.__supported_formats():
                raise RuntimeError(f"Unsupported partition format '{self.format}'")

            options = next(ast.find_data("partition_options"), None)
            if options is not None:
                self.options = options.children[0].value.strip('"')
            else:
                self.options = ""
        else:
            self.format = None
            self.options = ""

        mount = next(ast.find_data("partition_mount"), None)
        if mount is not None:
            self.mount = mount.children[0].value
        else:
            self.mount = None

        size = next(ast.find_data("partition_size"), None)
        if size is not None:
            self.units = size.children[1].value.upper()
            self.size = int(size.children[0].value)
        else:
            self.units = None
            self.size = None

        flags = next(ast.find_data("partition_flags"), None)
        if flags is not None:
            self.flags = [child.value.lower() for child in flags.children]
        else:
            self.flags = None

    def __supported_formats(self) -> List[str]:
        return ["ext2", "ext3", "ext4", "xfs"]

    def commands(self, builder: "ImageBuilder") -> Sequence[editor.Command]:
        partition_cmd = ""
        if self.size is not None:
            partition_cmd += f"size={self.size}{self.units},"

        if self.flags is not None:
            for flag in self.flags:
                if flag == "boot":
                    partition_cmd += "bootable,"
                elif flag == "efi":
                    partition_cmd += "type=U,"
                elif flag == "bios_grub":
                    # The BIOS boot GPT GUID
                    partition_cmd += "type=21686148-6449-6E6F-744E-656564454649,"

        # Mark anything that doesn't have an explicit type as Linux
        if partition_cmd == "":
            partition_cmd += "type=L,"

        commands = [
            editor.GuestCommand(
                f"echo '{partition_cmd}' | sfdisk /dev/sda -a",
                builder.editor.ssh_config,
                builder.config.ssh_timeout,
            )
        ]

        if self.format is not None:
            commands.append(
                editor.GuestCommand(
                    f"mkfs.{self.format} {self.options} /dev/sda{self.number}",
                    builder.editor.ssh_config,
                    builder.config.ssh_timeout,
                )
            )

        return commands

    def __str__(self) -> str:
        output = f"PARTITION {self.number} "
        if self.size is not None:
            output += f"SIZE {self.size}MB "
        if self.format is not None:
            output += f"FORMAT {self.format} "
        if self.options != "":
            output += f'OPTIONS "{self.options}" '
        if self.mount is not None:
            output += f"MOUNT {self.mount} "
        if self.flags is not None:
            output += "FLAGS "
            for flag in self.flags:
                output += f"{flag} "
        return output.strip()


class FromInstruction(ImageInstruction):
    source: str

    def __init__(self, ast: lark.tree.Tree) -> None:
        self.source = ast.children[0].value

    def __str__(self) -> str:
        return f"FROM {self.source}"


def _build_instruction(ast: lark.tree.Tree) -> ImageInstruction:
    cmd = ast.children[0]
    if cmd.data == "run":
        return RunInstruction(cmd)
    elif cmd.data == "inspect":
        return InspectInstruction(cmd)
    elif cmd.data == "copy":
        return CopyInstruction(cmd)
    elif cmd.data == "add":
        return AddInstruction(cmd)
    elif cmd.data == "disk":
        return DiskInstruction(cmd)
    elif cmd.data == "partition":
        return PartitionInstruction(cmd)
    elif cmd.data == "from":
        return FromInstruction(cmd)
    else:
        raise RuntimeError(f"Unsupported build instruction: '{cmd.data}'")


T = TypeVar("T")


class ImageBuilder:
    config: configuration.Config
    build_dir: str
    store: image.ImageStore
    instructions: List[ImageInstruction]
    qemu: qemu.QemuRunner
    from_instruction: FromInstruction
    chroot_ready: bool
    editor: editor.ImageEditor

    def __init__(self, config: configuration.Config, store: image.ImageStore) -> None:
        self.chroot_ready = False
        self.config = config
        self.store = store

        if config.file is None:
            imagefile_path = os.path.join(self.config.build_dir, "Imagefile")
        else:
            imagefile_path = config.file

        logging.info(f"Parsing Imagefile at '{imagefile_path}'")
        with open(imagefile_path, "r") as file:
            contents = file.read()
            parsed = IMAGEFILE_PARSER(contents)
            self.instructions = [
                _build_instruction(instr) for instr in parsed.find_data("instruction")
            ]

        logging.info("Validating Imagefile")
        self.__validate()

    def __is_from_scratch(self) -> bool:
        return self.from_instruction.source.lower() == "scratch"

    def __instruction_type(self, instr_type: Type[T]) -> List[T]:
        return [instr for instr in self.instructions if isinstance(instr, instr_type)]

    def __validate(self) -> None:
        from_instructions = self.__instruction_type(FromInstruction)
        if len(from_instructions) != 1:
            raise RuntimeError("Exactly one FROM instruction must appear per Imagefile")
        self.from_instruction = from_instructions[0]

        disk_instructions = self.__instruction_type(DiskInstruction)
        part_instructions = self.__instruction_type(PartitionInstruction)

        if len(disk_instructions) > 1:
            raise RuntimeError("Only one DISK instruction can appear per Imagefile")

        if self.__is_from_scratch():
            if len(disk_instructions) == 0:
                raise RuntimeError(
                    "Exactly one DISK instruction must appear in images built from scratch"
                )
            if len(part_instructions) == 0:
                raise RuntimeError(
                    "At least one PARTITION instruction must appear in images built from scratch"
                )
            if not any([instr.mount == "/" for instr in part_instructions]):
                raise RuntimeError("At least one PARTITION instruction must mount at /")
        elif len(disk_instructions) > 0 or len(part_instructions) > 0:
            raise RuntimeError(
                "DISK and PARTITION instructions can only appear on images built from scratch"
            )

        # Simple state machine to ensure the Imagefile is in a rational order
        class ImagefileSection(enum.Enum):
            FROM = (0,)
            DISK = (1,)
            PARTITION = (2,)
            EXECUTE = 3

        section = None
        for instr in self.instructions:
            if isinstance(instr, FromInstruction):
                if section is not None:
                    raise RuntimeError(
                        "FROM instruction must appear before any other instructions"
                    )
                else:
                    section = ImagefileSection.FROM
                    continue
            elif isinstance(instr, DiskInstruction):
                if section != ImagefileSection.FROM:
                    raise RuntimeError(
                        "DISK instruction must appear immediately after FROM instruction"
                    )
                else:
                    section = ImagefileSection.DISK
                    continue
            elif isinstance(instr, PartitionInstruction):
                if (
                    section != ImagefileSection.DISK
                    and section != ImagefileSection.PARTITION
                ):
                    raise RuntimeError(
                        "PARTITION instructions must appear immediately after DISK instruction"
                    )
                else:
                    section = ImagefileSection.PARTITION
                    continue
            else:
                section = ImagefileSection.EXECUTE

    def __print_step(self, instruction: ImageInstruction) -> None:
        total_steps = len(self.instructions)
        idx = self.instructions.index(instruction) + 1
        print(f"Step {idx}/{total_steps} : {instruction}")

    def __prepare_new_image(self) -> str:
        self.__print_step(self.from_instruction)

        name = image.storage_safe_encode(self.config.name)
        if self.config.local is True:
            # If this is a local (non-backend) build, then use the build dir for
            # the working image as well, so we can atomically rename at the end
            working = os.path.join(self.config.build_dir, f"{name}.working")
        else:
            working = os.path.join(self.store.working, name)

        if not self.__is_from_scratch():
            existing = self.store.retrieve_image(self.from_instruction.source).path
            logging.info(f"Copying backend file as base of new image at '{working}'")
            with open(existing, "rb") as source, open(working, "wb") as dest:
                # Get the size of the source for the progress bar
                size = source.seek(0, os.SEEK_END)
                source.seek(0)
                utils.copy_with_progress(source, dest, size)
        else:
            logging.info(f"Creating new image at '{working}'")
            disk = self.__instruction_type(DiskInstruction)[0]

            self.__print_step(disk)

            utils.run_check_retcode(
                [
                    self.store.qemu_img_bin,
                    "create",
                    "-f",
                    "qcow2",
                    working,
                    f"{disk.size}{disk.units}",
                ]
            )
        return working

    def __inspect_guest_chroot(self) -> None:
        config = self.editor.ssh_config.override(
            args=[*self.editor.ssh_config.args, "-t"]
        )
        client = ssh.SshClient(
            config, command="unshare --fork --pid chroot /mnt /bin/bash"
        )

        # Connect everything normally
        handle = client.connect(
            self.config.ssh_timeout, stdin=None, stdout=None, stderr=None
        )

        # Wait until the user chooses to exit
        handle.wait()

    def __prepare_chroot(self) -> None:
        # Adapted from arch-chroot
        self.editor.run_command_in_guest(
            [
                'mount udev "/mnt/dev" -t devtmpfs -o mode=0755,nosuid',
                'mount proc "/mnt/proc" -t proc -o nosuid,noexec,nodev',
                'mount sys "/mnt/sys" -t sysfs -o nosuid,noexec,nodev,ro',
                'mount devpts "/mnt/dev/pts" -t devpts -o mode=0620,gid=5,nosuid,noexec',
                'mount shm "/mnt/dev/shm" -t tmpfs -o mode=1777,nosuid,nodev',
                'mount /run "/mnt/run" --bind',
                'mount tmp "/mnt/tmp" -t tmpfs -o mode=1777,strictatime,nodev,nosuid',
                "(mount /etc/resolv.conf /mnt/etc/resolv.conf --bind || cp /etc/resolv.conf /mnt/etc/resolv.conf)",
            ],
            allowfail=True,
        )

        # Some images (RHEL/CentOS) may require selinux labeling. If files are created
        # without the appropriate labels, the filesystem will require re-labeling which
        # can be time-consuming. To avoid this, always attempt to load a policy in the
        # context of the guest before executing any user commands
        self.__run_command_in_guest_chroot("load_policy -i", allowfail=True)
        self.chroot_ready = True

    def __partition_instructions_by_mount(
        self, instructions: List[PartitionInstruction]
    ) -> List[PartitionInstruction]:
        mountable = [instr for instr in instructions if instr.mount is not None]

        def sort_key(instr: PartitionInstruction) -> int:
            assert instr.mount is not None
            return len(pathlib.Path(instr.mount).parts)

        return sorted(mountable, key=sort_key)

    def __prepare_chroot_early(self) -> None:
        disk_cmd = self.__instruction_type(DiskInstruction)[0]
        for cmd in disk_cmd.commands(self):
            cmd.run()

        partition_instructions = self.__instruction_type(PartitionInstruction)
        for partition_instr in partition_instructions:
            self.__print_step(partition_instr)
            for cmd in partition_instr.commands(self):
                cmd.run()

        # Now that the partitions are created and formatted, mount them in the
        # required order
        ordered_partitions = self.__partition_instructions_by_mount(
            partition_instructions
        )
        for partition_instr in ordered_partitions:
            self.editor.run_command_in_guest(
                f"mkdir -p /mnt/{partition_instr.mount}", allowfail=True
            )
            self.editor.run_command_in_guest(
                f"mount /dev/sda{partition_instr.number} /mnt/{partition_instr.mount}"
            )

    def __is_executable_instruction(self, instr: ImageInstruction) -> bool:
        return isinstance(instr, RunInstruction) or isinstance(instr, InspectInstruction)

    def __run_command_in_guest_chroot(
        self,
        command: Union[str, List[str]],
        allowfail: bool = False,
        capture_stdout: bool = False,
        capture_stderr: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(command, list):
            single_cmd = editor.combine_commands(command, allowfail)
        else:
            single_cmd = command
        try:
            return GuestChrootCommand(
                single_cmd,
                self.editor.ssh_config,
                self.config.ssh_timeout,
                capture_stdout=capture_stdout,
                capture_stderr=capture_stderr,
            ).run()
        except:
            if allowfail is False:
                raise
            return None, None

    def build(self) -> str:
        new_image = self.__prepare_new_image()

        self.editor = editor.ImageEditor(self.config, new_image, self.__is_from_scratch())

        # Start the image editor
        self.editor.edit()

        # Mount the partitions to the expected locations, but don't do any other
        # mounts in the chroot (/dev, /tmp, etc) because if this is a FROM scratch
        # build, those locations won't exit yet.
        if self.__is_from_scratch():
            self.__prepare_chroot_early()

        for instr in self.instructions:
            # FROM, DISK and PARTITION instructions have already been handled
            if (
                isinstance(instr, FromInstruction)
                or isinstance(instr, DiskInstruction)
                or isinstance(instr, PartitionInstruction)
            ):
                continue
            elif self.__is_executable_instruction(instr) and self.chroot_ready is False:
                # Now that we have a RUN instruction, the extraction of the base
                # filesystem must have happened, so we can finish preparing
                # the chroot.
                self.__prepare_chroot()

            self.__print_step(instr)

            # If this is an inspect instruction, don't try to run anything
            if isinstance(instr, InspectInstruction):
                self.__inspect_guest_chroot()
                continue

            for cmd in instr.commands(self):
                cmd.run()

        self.editor.close()

        # Everything is done. Move the built image to its destination
        if self.config.local is True:
            destination = os.path.join(self.config.build_dir, f"{self.config.name}.qcow2")
        else:
            destination = self.store.backend_path(image.ImageSpec(self.config.name))

        # Make the new image read-only before moving.
        os.chmod(new_image, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        os.rename(new_image, destination)

        return destination
