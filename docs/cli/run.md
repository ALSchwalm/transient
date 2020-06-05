## Run

The `run` subcommand for `transient` provides the way to actually start
a virtual machine and connect to it. This is largely achieved by calling
directly to QEMU.


When a disk image is specified via the `-image` flag, a few things happen:

1. `transient` checks for the existence of a disk of the provided image type,
associated with the given vm name in the Disk Frontend.

2. If no such disk exists, `transient` checks the Disk Backend for a disk of
the provided image type. If the disk exists in the backend, a copy is made in
to the frontend and associated with the VM name.

3. If there is no such disk in the Disk Backend, then `transient` will attempt
to download the disk. Currently the only support image types are Vagrant libvirt
boxes. As such, `transient` will connect to Vagrant cloud and attempt to download
the box. The downloaded image is placed in the Disk Backend and a VM-specific copy
is placed in the Disk Frontend.

Once the disk has been created, `transient` passes the new disk as an additional
argument on the QEMU commandline. Because the image in the Disk Frontend is
associated with the virtual machien name, subsequent invocations of `transient`
with the same `name` and disk `-image` flags will boot using the same images.

When `transient` starts a virtual machine, it will acutomatically connect the
user to either the QEMU process or an SSH connection with the VM. Which one is
determined by the flags described below. But regardless of the connection type,
once the user is no longer connect (e.g., the ssh connection is termianted),
`transient` **automatically shuts down the virtual machine**.

### Usage

`transient run [FLAGS] -- [QEMU ARGS]`

`transient` supports a number of flags that add features to the QEMU virtual
machine. These options are described below:

- `-name NAME`: Associated downloaded disk images with `NAME`. Subsequent invocations
of `transient` with the same name and `-image` flags will boot with the same disks.

- `-image IMAGESPEC`: Downloads the requested virtual disk to backend and
creates a copy in the disk frontend. This disk will be passed to the virtual machine.
For additional information, see [Getting Images](/details/images/).

- `-image-frontend FRONTEND`: Use the provided `FRONTEND` path as the location to
place the per-vm image copies. Note: this path defaults to
`~/.local/share/transient/frontend`.

- `-image-backend BACKEND`: Use the provided `BACKEND` path as the location to
place the read-only backing images. Note: this path defaults to
`~/.local/share/transient/backend`.

- `-ssh-console`: Instead of connecting the user to the QEMU serial console or
VNC output, `transient` waits for an SSH connection to be established with the
guest then connects standard input/output to that SSH connection. This connection
is, by default, authenticated using the normal Vagrant public/private keys.

- `-ssh-user USER`: Pass `USER` as the username when making an SSH connection to the
virtual machine (e.g., with `-ssh-console`).

- `-ssh-bin-name NAME`: Use `NAME` instead of `ssh` when making an SSH connection
with the virtual machine.

- `-ssh-timeout TIMEOUT`: Wait `TIMEOUT` seconds when attempting to make an SSH
connection with the virtual machine before failing. Defaults to 90 seconds.

- `-ssh-port PORT`: Connect to port `PORT` on the virtual machine for SSH instead of
the default 22.

- `-ssh-command COMMAND`: Instead of connecting standard input and output to the SSH
connection with the virtual machine, pass `COMMAND` instead. (e.g., `ssh vagrant@vm-ip COMMAND`)

- `-shutdown-timeout`: When the user exits an SSH console, `transient` sends an ACPI
shutdown event and waits for this time for the guest to shutdown cleanly. After this
timeout, the guest is terminated.

- `-shared-folder FOLDERSPEC`: A `FOLDERSPEC` consists of two paths joined with a colon.
For example `/path/on/host:/path/on/guest`. For additional information, see [Using
Shared Folders](/details/shared-folders/).

- `-prepare-only`: `transient` will exit after performing the disk download/creation
steps outlined above. It will not start the guest virtual machine.

- `-copy-in-before`: Copy the contents of a host directory to a location on the guest
before booting the VM. For example `-copy-in-before path/on/host:/path/on/guest`

- `-copy-out-after`: Copy the contents of a guest directory to a location on the hose
after shutting down the VM. For example `-copy-out-after path/on/host:/path/on/guest`

#### Examples

##### Run a CentOS 7 VM with Serial Console

```
$ transient run \
   -name test-vm \
   -image centos/7:2004.01 \
   -- \
   -nographic -enable-kvm -m 1G
Unable to find image 'centos/7:2004.01' in backend
Pulling from vagranthub: centos/7:2004.01
100% |##############################################|  11.6 MiB/s | 439.1 MiB | Time:  0:00:37
Download completed. Starting image extraction.
100% |##############################################| 218.7 MiB/s |   1.1 GiB | Time:  0:00:04
Finished preparation. Starting virtual machine
[    0.000000] Initializing cgroup subsys cpuset
[    0.000000] Initializing cgroup subsys cpu
[    0.000000] Initializing cgroup subsys cpuacct
[    0.000000] Linux version 3.10.0-1127.el7.x86_64 (mockbuild@kbuilder.bsys.centos.org) (gcc 0
[    0.000000] Command line: BOOT_IMAGE=/boot/vmlinuz-3.10.0-1127.el7.x86_64 root=UUID=1c419d68
[    0.000000] e820: BIOS-provided physical RAM map:
... SNIP ...
[  OK  ] Started OpenSSH server daemon.
[  OK  ] Started Dynamic System Tuning Daemon.
[  OK  ] Started Postfix Mail Transport Agent.
[  OK  ] Reached target Multi-User System.
         Starting Update UTMP about System Runlevel Changes...
[  OK  ] Started Update UTMP about System Runlevel Changes.

CentOS Linux 7 (Core)
Kernel 3.10.0-1127.el7.x86_64 on an x86_64
localhost login:
```

##### Run a CentOS 7 VM with SSH

```
$ transient run \
   -name test-vm \
   -image centos/7:2004.01 -ssh-console \
   -- \
   -nographic -enable-kvm -m 1G
100% |##############################################|  11.6 MiB/s | 439.1 MiB | Time:  0:00:37
Download completed. Starting image extraction.
100% |##############################################| 218.7 MiB/s |   1.1 GiB | Time:  0:00:04
Finished preparation. Starting virtual machine
[vagrant@localhost ~]$
```