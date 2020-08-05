## Imagefile Format

`transient` image builds are defined using a declarative format similar to
the Dockerfile. Each `Imagefile` is made of a series of commands that may
consist of a number of parts. For more information on _how_ these commands
are executed, see the [Building Images page](./building.md).

`Imagefile`s currently support the following commands:

### FROM

The `FROM` command has two forms and is required in every `Imagefile`:

- `FROM <baseimage>`
- `FROM scratch`

The first form defines an image that is derived from the specified `baseimage`.
These can be specified using the same format as the `-image` flag to the `run`
command line subcommand.

The second form defines a 'base' image. When using this form, the next command
_must_ be a `DISK` command which will specify the size of the new disk.

### DISK

The `DISK` command has one form, and can only be used with `FROM scratch` images:

- `DISK <size> <units> <type>`

These specify the size of the new disk in terms of `<units>` as well as whether
the partition table is "GPT" or "MBR". For example:

```
DISK 20 GB MBR
```

The above command specifies a new disk that is 20GB with an "MBR" formatted
partition table. Supported `<units` are `GB` and `MB`. Supported `<type>` are
`GPT` and `MBR`. The `DISK` command must be followed by one or more `PARTITION`
commands.

### PARTITION

The `PARTITION` command has the following form:

- `PARTITION <number> [SIZE <size>] [FORMAT <format> [OPTIONS <options>]] [MOUNT <mount>] [FLAGS <flags>]`

These optional fields have the following meaning:

- `SIZE <size>`: Specify the size of the partition. This is specified as a size and unit,
with the same supported units as the `DISK` command, so `SIZE 10 GB` is a valid `SIZE`
field. If this field is omitted, the partition will span the entire disk.

- `FORMAT <format> [OPTIONS <options>]`: Once the parition has been created, if
this field exists, the partition will be formatted via `mkfs.<format>`. Otherwise,
the parition is not formatted. Currently, the supported formats are `xfs`, `ext2`,
`ext3` and `ext4`. If the `OPTIONS` field is passed, the `<options>` string will be
passed directly to the format command. For example:
`PARTITION 1 FORMAT xfs OPTIONS "-m crc=0"` will execute `mkfs.xfs -m crc=0` when
formatting the partition.

- `MOUNT <mountpoint>`: The `MOUNT` field of the `PARTITION` command specifies the
mount location of this partition. If this field is not present, the partition is
not mounted during the build.

- `FLAGS [<flag> [,<flag>] ...]`: Specify one or more flags to be set for this
partition. Valid flags are `boot`, `efi` and `bios_grub`.

### COPY

The `COPY` command has one form:

- `COPY <source> <destination>`

This command copies a file from a path relative to the `BUILD_DIR` (see the
[build command page](../cli/build.md)) to the `<destination>` path in the
new image.

### ADD

The `ADD` command has one form:

- `ADD <source> <destination>`

This command is very similar to the `COPY` command. It copies a file from a path
relative to the `BUILD_DIR` to the `<destination>` path in the new image. However,
unlike `COPY`, the `ADD` command will also extract any compressed archives. The
`ADD` command is typically used when building a `FROM scratch` image to add the
initial minimal filesystem.

### RUN

The `RUN` command has one form:

- `RUN <command>`

`RUN` executes the given command as root in the context of the new image. That is,
`transient` will first perform a `chroot` in to the new image before executing
the command.

### INSPECT

The `INSPECT` command has one form and takes no arguments:

- `INSPECT`

The `INSPECT` command is a debugging utility for building images. It is sometimes
unclear what is causing a `RUN` command to fail when building an image. For this
reason, if the user encounters an unexpected failure, they can add the `INSPECT`
command before the `RUN` command that fails. This will cause `transient` to
drop to a console instead of executing the `RUN` command. The user may then
inspect the state of the guest image. After the user `exit`s the shell, the
build will continue as normal.
