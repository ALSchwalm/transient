## Shared Folders

`transient` supports a mechanism for sharing host directories with a virtual machine.
[`sshfs`](https://github.com/libfuse/sshfs) is the underlying sharing mechanism, which
is a FUSE filesystem that uses `ssh` to perform the actual file transfer.

A shared folder can be created with a guest by specifying `-shared-folder` on the
`transient run` command line. This will cause the `transient` to perform a series of
operations:

1. Establish an SSH connection with the guest
2. Use the guest's `sshfs` application to mount the requested host folder to the
   requested guest path, piping data between it and the host's `sftp-server`

This logic implies a few requirements for using shared folders in `transient`.

#### Requirements

Because `transient` directly runs the host's sftp server, it searches various standard
locations for `sftp-server`. If the host's server has a nonstandard name or location,
the argument `-sftp-bin-name` must be used to specify either an absolute path or a
file name that resides in the system's PATH.

`transient` also requires that the guest image have `sshfs` installed. To build a
guest image with `sshfs` pre-installed, see [Building Images](../images/building)
