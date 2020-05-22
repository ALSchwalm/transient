# Transient Documentation

`transient` is a thin wrapper around QEMU intended to provide higher level
features like disk image downloads and shared folders, without the complexity
of existing VM management solutions. `transient` is, as the name suggests,
focused on creating virtual machines for test and development purposes that
typically run for very short times. In fact `transient` will automatically
stop any virtual machine it starts once the user is no longer connected to it.

## Concepts

`transient` adds a few concepts on top of QEMU. The most significant of these
is the virtual machine name (set via the required `-name` parameter). The name
is how `transient` is able to save changes made to the disks connected to the
VM. When a disk image is specified via the `-image` flag, a few things happen:

1. `transient` checks for the existence of a disk of the provided image type,
associated with the given vm name in the Disk Frontend.

2. If no such disk exists, `transient` checks the Disk Backend for a disk of
the provided image type. If the disk exists in the backend, a copy is made in
to the frontend and associated with the VM name.

3. If there is no such disk in the Disk Backend, then `transient` will attempt
to download the disk. Currently the only support image types are Vagrant boxes.
As such, `transient` will connect to Vagrant cloud and attempt to download the
box. The downloaded image is placed in the Disk Backend and a VM-specific copy
is placed in the Disk Frontend.

Once the disk has been created, `transient` passes the new disk as an additional
argument on the QEMU commandline. Because the image in the Disk Frontend is
associated with the name, subsequent invocations of `transient` with the same `name`
and disk `-image` flags will boot using the same images.

The Disk Frontend and Disk Backend are both located at `~/.local/share/transient`
by default, and are the _only_ persistent state created by `transient`. This
dramatically simplifies creating short lived virtual machines that need some
degree of persistence. Simply specify a custom Disk Frontend with the
`-image-frontend` argument and boot your virtual machine. Once you are finished,
just delete the Disk Frontend you specified and the virtual machine is entirely
gone.

## Usage

```
usage: transient [OPTIONS] -- [ARG [ARG ...]]

A simple libvirt/vagrant alternative

positional arguments:
  ARG                   Arguments passed directly to QEMU

optional arguments:
  -h, --help            show this help message and exit
  -version, --version   show program's version number and exit
  -v, --verbose         Verbosity level (repeat to be more verbose)
  -name NAME            Set the vm name
  -image IMG [IMG ...]  Disk image to use (this option can be repeated)
  -image-frontend IMAGE_FRONTEND
                        The location to place per-vm disk images
  -image-backend IMAGE_BACKEND
                        The location to place the shared, read-only backing disk images
  -ssh-console, -ssh    Use an ssh connection instead of the serial console
  -ssh-with-serial, -sshs
                        Show the serial output before SSH connects (implies -ssh)
  -ssh-user SSH_USER, -u SSH_USER
                        User to pass to SSH
  -ssh-bin-name SSH_BIN_NAME
                        SSH binary to use
  -ssh-timeout SSH_TIMEOUT
                        Time to wait for SSH connection before failing
  -ssh-port SSH_PORT    Local port the 22 of the guest is forwarded to
  -ssh-command SSH_COMMAND, -cmd SSH_COMMAND
                        Run an ssh command instead of a console
  -sync-before SYNC_BEFORE [SYNC_BEFORE ...], -b SYNC_BEFORE [SYNC_BEFORE ...]
                        Sync a host path to a guest path before starting the guest
  -sync-after SYNC_AFTER [SYNC_AFTER ...], -a SYNC_AFTER [SYNC_AFTER ...]
                        Sync a guest path to a host path after stopping the guest
  -shared-folder SHARED_FOLDER [SHARED_FOLDER ...], -s SHARED_FOLDER [SHARED_FOLDER ...]
                        Share a host directory with the guest (/path/on/host:/path/on/guest)
  -prepare-only         Only download/create vm disks. Do not start the vm
```
