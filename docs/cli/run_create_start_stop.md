## VM Creation and Execution

`transient` supports two ways of starting virtual machines. The simplest
way is to use the `transient run` subcommand. This will create a short-lived
virtual machine that will be automatically removed when the user exits
their connection to it (unless a long term `--name` is provided, as describd
below). This is useful for test scenarios that don't require execution of the
same VM multiple times.

When the same VM must be able to be started/stopped multiple times, use
the `transient create` command to build the VM, then start with
`transient start`. The VM will be shutdown when a users exits their connection,
but it will not be removed completely. So, a subsequent `transient start <name>`
can be used to start the same VM again.

### VM Storage

`transient` is designed to carefully control where state is stored on the
system. This is necessary so test infrastructure using `transient` can
be sure that various disks and other files are correctly cleaned up between
test runs. Transient stores files in the following ways:

#### Backend Disk Images

Read-only backend disk images are always stored in the Disk Backend. These
disks are never used directly by virtual machines, but are used as the
copy-on-write backing files for the per-VM disks that are actually attached
to the VMs.

#### VM Disk Images and Configuration:

- For a VM created with `transient run` and not given a name,
`transient` will not store any state on disk. The temporary disk used by
the VM will be backed by RAM, and made using the QEMU `-snapshot` flag.
- For a VM created with `transient create` or `transient run --name <name>`,
the VM state and configuration will be stored in the VM Store

### VM Image Retrieval

When a `transient` command like `create` is invoked, a few things happen to ensure
the relevant disk is available:

1. `transient` checks the Disk Backend for a disk of the provided image type. If
the disk exists in the backend, a (copy-on-write) copy is made in the VM store
and associated with the VM name.

2. If there is no such disk in the Disk Backend, then `transient` will attempt
to download the disk using the specified protocol and place it in the disk
backend. A (copy-on-write) copy is then made in the VM store and associated with
the VM name.

Once the disk has been created, `transient` passes the new disk as an additional
argument on the QEMU command line. Because the image in the VM store is
associated with the virtual machine name, subsequent `start`s of the same VM will
use the existing disks.

When `transient` starts a virtual machine, it will automatically connect the
user to either the QEMU process or an SSH connection with the VM. The connection
type is determined by the flags described below. But regardless of the connection
type, once the user is no longer connect (e.g., the ssh connection is terminated),
`transient` **automatically shuts down the virtual machine**.

### Usage

#### Common VM Execution Flags

`transient run` and `transient start` support a very similar set of flags. The
ones common to both subcommands are described below:

- `--ssh-user SSH_USER`: User to pass to SSH [default: vagrant]
- `--ssh-bin-name SSH_BIN_NAME`: SSH binary to use [default: ssh]
- `--ssh-timeout SSH_TIMEOUT`:  Time to wait for SSH connection before failing [default: 90]
- `--ssh-command SSH_COMMAND`:  Run an ssh command instead of a console
- `--ssh-option SSH_OPTION`: Pass an option to SSH
- `--verbose, -v`: Verbosity level for logging
- `--vmstore VMSTORE` :Location to place VM images and configuration files
                       [default: ~/.local/share/transient/vmstore]
- `--image-backend IMAGE_BACKEND`: Location to place the shared, read-only backing disk
                                  images [default: ~/.local/share/transient/backend]
- `--ssh-console, --ssh`: Use an ssh connection instead of the serial console
- `--ssh-with-serial, --sshs`: Show the serial output before SSH connects (implies --ssh)
- `--sftp-bin-name SFTP_BIN_NAME`:SFTP server binary to use [default: sftp-server]
- `--ssh-port SSH_PORT`: Host port the guest port 22 is connected to
- `--ssh-net-driver SSH_NET_DRIVER`: The QEMU virtual network device driver e.g. e1000,
                                     rtl8139, virtio-net-pci [default: virtio-net-pci]
- `--no-virtio-scsi`: Use the QEMU default drive interface (ide) instead of virtio-pci-scsi
- `--shutdown-timeout SHUTDOWN_TIMEOUT`: The time in seconds to wait for shutdown before
                                         terminating QEMU [default: 20]
- `--qemu-bin-name QEMU_BIN_NAME`: QEMU binary to use [default: qemu-system-x86_64]
- `--qmp-timeout QMP_TIMEOUT`: The time in seconds to wait for the QEMU QMP connection to
                               be established [default: 10]
- `--shared-folder SHARED_FOLDER`: Share a host directory with the guest
                                   (/path/on/host:/path/on/guest)
- `--config CONFIG`: Path to a config toml file to read parameters from. (see [Config Format](../details/config-file.md) for details)
- `--copy-in-before COPY_IN_BEFORE`: Copy a file or directory into the VM before running
                                     (path/on/host:/absolute/path/on/guest)
- `--copy-out-after COPY_OUT_AFTER`: Copy a file or directory out of the VM after running
                                     (/absolute/path/on/VM:path/on/host)
- `--copy-timeout COPY_TIMEOUT`: The maximum time to wait for a copy-in-before or
                                 copy-out-after operation to complete
- `--direct-copy`:    Transfier files specified via `--copy-in-before` or `--copy-in-after` directly to the VM, instead of a background 'builder' VM
- `--rsync`: Use rsync for copy-in-before/copy-out-after operations

#### VM Creation Flags

When creating a VM via `transient create`, most of the above flags can be specified.
This will cause `transient start` to run the VM with the requested behavior. For
example, if a VM is created like:

```
$ transient create generic/alpine38:v3.0.2 --name my-vm --ssh -- <other qemu args>
```

Then a subsequent `start` command will connect to the VM using SSH and with the
specified QEMU arguments:

```
$ transient start my-vm
```

However, some flags can _only_ be specified during execution of a VM via `transient start`
or `transient run`. The following flags cannot be specified during creation, as it is
unclear what the desired behavior would be: `--copy-in-before`, `--copy-out-after`.

Additionally, some flags can only be specified during creation, not when the VM is
started. The following flags behave this way:

- `--extra-image EXTRA_IMAGE`: Add an extra disk image to the VM. The format of
                               `EXTRA_IMAGE` argument is identical to the primary
                               image specified during creation.

#### Stopping a VM

```
transient stop [-h] [--verbose] [--vmstore VMSTORE] [--image-backend IMAGE_BACKEND]
               [--kill]
               name [name ...]
```

Unlike the `start`, `run` and `create` commands, `stop` has very few flags. They are
described below:

- `name`: The name(s) of the VM to stop

- `--vmstore VMSTORE`: Search the provided VMSTORE for the given VM name

- `--kill`: Send `SIGKILL` instead of `SIGTERM`

### Examples

### Create and Start an Alpine VM

```
$ transient create --name bar --ssh alpine_rel3,http=https://github.com/ALSchwalm/transient-baseimages/releases/download/6/alpine-3.13.qcow2.xz
Unable to find image 'alpine' in backend
Downloading image from 'https://github.com/ALSchwalm/transient-baseimages/releases/download/5/alpine-3.13.qcow2.xz'
100% |##############################################|  12.7 MiB/s |  35.0 MiB | Time:  0:00:02
Created VM 'test'
$ transient start bar
Finished preparation. Starting virtual machine
alpine-3_13:~$
```

#### Run a CentOS 7 VM with Serial Console

```
$ transient run centos/7:2004.01 --name test-vm \
   -- -nographic -enable-kvm -m 1G
Unable to find image 'centos/7:2004.01' in backend
Pulling from vagrant cloud: centos/7:2004.01
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

#### Run a CentOS 7 VM with SSH

```
$ transient run centos/7:2004.01 --name test-vm --ssh-console \
   -- \
   -nographic -enable-kvm -m 1G
100% |##############################################|  11.6 MiB/s | 439.1 MiB | Time:  0:00:37
Download completed. Starting image extraction.
100% |##############################################| 218.7 MiB/s |   1.1 GiB | Time:  0:00:04
Finished preparation. Starting virtual machine
[vagrant@localhost ~]$
```

#### Stopping a running VM

```
$ transient stop my-vm
```
