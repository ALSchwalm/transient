## PS

The `cp` subcommand of `transient` allows the user to copy files to or from
offline virtual machines.

### Usage

```
usage: transient cp [-h] [--verbose] [--vmstore VMSTORE] [--image-backend IMAGE_BACKEND]
                    [--rsync]
                    path [path ...]
```

- `path`: Path to copy to or from. Paths can either be local (e.g. `/root/myfile`)
or VM-based (e.g., `MY_VM_NAME:/etc/fstab`). Either the destination or the source
must be VM-based

- `--rsync`: Use `rsync` for copy operations (instead of `scp`)

- `--vmstore VMSTORE`: Copy to VMs backed by the provided `VMSTORE` path

- `--image-backend BACKEND`: Use the provided `BACKEND` path as the location
to search for existing images

### Examples

#### Copying a file to a VM

```
$ transient cp example test-vm:/root/
example                                                      100%    5     1.4KB/s   00:00
```

#### Copying a file from a VM

```
$ transient cp test-vm:/etc/fstab .
fstab                                                        100%   24     6.5KB/s   00:00
```
