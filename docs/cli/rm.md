## RM

The `rm` subcommand for `transient` provides a way to remove previously
created virtual machines

### Usage

```
transient rm [-h] [--verbose] [--vmstore VMSTORE] [--image-backend IMAGE_BACKEND]
             [--force]
             name [name ...]
```

- `name`: The VM name of the VM(s) to remove

- `--vmstore VMSTORE`: Search the provided `VMSTORE` path for VMs with the given
name

- `--force`: By default, `transient` will not allow removal of a running VM. With
this flag, it will stop the VM before removing

### Examples

#### Remove a VM that is not running

```
$ transient ps -a
 NAME     IMAGE                    STATUS
 example  alpine_rel3              Offline
 bar      alpine_rel3              Offline
 test-vm  generic/alpine38:v3.0.2  Offline
$ transient rm bar
$ transient ps -a
 NAME     IMAGE                    STATUS
 example  alpine_rel3              Offline
 test-vm  generic/alpine38:v3.0.2  Offline
```

#### Attempt to remove a running VM

```
$ transient ps
 NAME     IMAGE        STATUS
 example  alpine_rel3  Started 2021-08-16 17:45:51
$ transient rm example
Unable to acquire lock for the VM named 'example'
It may be in use by another process
```

#### Force removal of a running VM

```
$ transient ps
 NAME     IMAGE        STATUS
 example  alpine_rel3  Started 2021-08-16 17:45:51
$ transient rm example --force
$
```