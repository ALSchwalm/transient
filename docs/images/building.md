## Building Images

This page describes the architecture of the image building subsystem of
`transient`. While this should not generally be necessary to know, it can
sometimes be helpful when debugging an image building failure. For
instructions on how to use the `build` subcommand of `transient`, see
[this page](../cli/build.md). For information on the `Imagefile` format,
see the [Imagefile format page](./format.md).

### Types of Builds

Images can be built two ways: from scratch or based on an existing image.
The latter is much more common that the former. When building using an
existing image, `transient` will download the image in the same way as
the `run` command. It then generates a new backend image by executing the
commands specified in the `Imagefile`.

Images built from scratch work in a similar way, but the `Imagefile` must
also specify the partitions and disk size.

### The Build Process

When building an image, `transient` performs the following setup steps:

1. Boot a kernel and initramfs bundled with `transient`, with a copy of the
base image (specified via the `FROM` command) attached. This is the 'build'
virtual machine.
2. Scan the attached image for partitions
3. Locate the `fstab` and use it to perform appropriate mounts

`transient` then executes the remaining commands in the context of the mounted
guest partitions. For images built from scratch, rather than copying a base
image, `transient` first prepares an empty disk of the specified size and
passes that empty disk to the build virtual machine.

The approach is generally necessary as `transient` does not have any
guaranteed way of logging in if it were to just boot the guest and attempt to
run the commands through, for example, a serial connection. It is important
to keep in mind that commands are actually running in the 'build' virtual
machine, especially when building from scratch. Because partition creation
is actually happening with the `transient` kernel, the created partition
could be incompatible with the guest kernel. It may be necessary to pass
additional flags to make the filesystems compatible with older kernels.
