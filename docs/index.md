# Transient

`transient` is a wrapper around QEMU intended to provide higher level features
like disk image downloads and shared folders, without the complexity of existing
VM management solutions. `transient` is, as the name suggests, focused on creating
virtual machines for test and development purposes that typically run for very
short times. In fact `transient` will automatically stop any virtual machine it
starts once the user is no longer connected to it.

## Concepts

`transient` adds a few concepts on top of the standard QEMU usage. The most
significant of these are:

- **Disk Backend**: When a new virtual disk type is specified (e.g.,
the vagrant `centos/7:2004.01` box), the disk image will be downloaded and
stored in the Disk Backend. Images at this location are read-only and will
not be changed by running virtual machines. The Disk Backend is located at
`~/.local/share/transient/backend` by default.

- **VM Store**: This is the location `transient` uses to store the
per-VM copies of disks in the Disk Backend and other VM configuraiton
information. Note that `transient` actually uses QEMU copy-on-write files to
avoid the expensive copy each time a new VM disk is created in the store.
The VM Store is located at `~/.local/share/transient/vmstore` by
default.
