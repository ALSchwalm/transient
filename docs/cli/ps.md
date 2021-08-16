## PS

The `ps` subcommand of `transient` allows the user to list running transient
virtual machines.

### Usage

```
transient ps [-h] [--verbose] [--vmstore VMSTORE] [--image-backend IMAGE_BACKEND] [-a]
             [--ssh] [--pid]
```

- `--vmstore VMSTORE`: List VMs backed by the provided `VMSTORE` path

- `--image-backend BACKEND`: Use the provided `BACKEND` path as the location
to search for existing images

- `-a,--all`: List all VMs instead of only running VMs

- `--ssh`: Include whether a VM can be connected to with `transient ssh` in the output

- `--pid`: Include a VMs PID in the output

### Examples

#### Listing running images

```
$ transient ps
 NAME     IMAGE        STATUS
 example  alpine_rel3  Started 2021-08-16 17:14:45
```

#### Listing all VMs in the Store

```
$ transient ps -a
 NAME     IMAGE                    STATUS
 example  alpine_rel3              Started 2021-08-16 17:14:45
 test-vm  generic/alpine38:v3.0.2  Offline
```
