## Commit

The `commit` subcommand can be used to convert VM state into a new
disk image. This can be useful when performing an initial 'provisioning'
step (e.g., to install a new kernel) before tests start. Using `commit`,
the user would:

1. Create a VM with the desired initial backend image
2. Do the installation/configuration required before testing can start
3. Stop the VM and `commit` the VM state as a new backend image
4. Run all tests using the 'provisioned' image

This can save significant time if the provisioning processes is slow.

### Usage

```
transient commit [-h] [--verbose] [--vmstore VMSTORE] [--image-backend IMAGE_BACKEND]
                 vm-name backend-name
```

- `vm-name`: The name of the VM to use as the new disk backend

- `backend-name`: The name of the new backend image to create

- `--vmstore VMSTORE`: Search the provided `VMSTORE` for the given `vm-name`

- `--image-backend BACKEND`: Store the new backend image in the provided `BACKEND` path

### Examples

#### Commit a VM image as a new backend

```
$ transient start test-vm
Finished preparation. Starting virtual machine
alpine38:~$ touch my-modifications
alpine38:~$ exit
logout
Connection to 127.0.0.1 closed.
$ transient commit test-vm my-new-backend
Converting vm image to new backend image 'my-new-backend'
    (100.00/100%)
$ transient image ls
 NAME                     VIRT SIZE   REAL SIZE
 centos/7:2004.01         40.00 GiB    1.05 GiB
 generic/alpine38:v3.0.2  32.00 GiB   99.69 MiB
 my-new-backend           32.00 GiB  215.89 MiB
 alpine_rel3              20.00 GiB  131.44 MiB
$ transient run my-new-backend --ssh-command ls -- -enable-kvm -smp 2 -m 2G
Finished preparation. Starting virtual machine
my-modifications
$
```