## Shared Folders

`transient` supports a mechanism for sharing host directories with a virtual machine.
[`sshfs`](https://github.com/libfuse/sshfs) is the underlying sharing mechanism, which
is a FUSE filesystem that uses `ssh` to perform the actual file transfer.

A shared folder can be created with a guest by specifying `-shared-folder` on the
`transient run` command line. This will cause the `transient` to perform a series of
operations:

1. Establish an SSH connection with the guest, using the `-A` flag to forward the
   authentication agent in to the guest
2. Use the guest's `sshfs` application to mount the requested host folder to the
   requested guest path

This logic implies a few requirements for using shared folders in `transient`.

#### Requirements

Because `transient` must be able to connect from the guest to the host with `ssh` (
unlike the normal `transient` connection, from the host to the guest), the current
user must be able to `ssh` to `localhost`. That is `ssh localhost` should work.
This can probably be achieved by simply adding the contents of `~/.ssh/id_rsa.pub`
to `~/.ssh/authorized_keys`.

`transient` also requires that the guest image have `sshfs` installed.
