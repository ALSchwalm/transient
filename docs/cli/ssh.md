## SSH

The `ssh` subcommand for `transient` allows a user to connect to a running
`transient` virtual machine by name.

### Usage

```
transient ssh [-h] [--verbose] [--vmstore VMSTORE] [--image-backend IMAGE_BACKEND]
              [--ssh-user SSH_USER] [--ssh-bin-name SSH_BIN_NAME]
              [--ssh-timeout SSH_TIMEOUT] [--ssh-command SSH_COMMAND]
              [--ssh-option SSH_OPTION] [--wait]
              name
```

- `name`: The name of the `transient` virtual machine to connect to

- `--ssh-timeout TIMEOUT`: Wait `TIMEOUT` seconds when attempting to make an SSH
connection with the virtual machine before failing. Defaults to 90 seconds.

- `--ssh-user USER`: Pass `USER` as the username when making an SSH connection to the
virtual machine.

- `--ssh-bin-name NAME`: Use `NAME` as the command instead of `ssh` when making an
SSH connection with the virtual machine.

- `--ssh-command COMMAND`: Instead of connecting standard input and output to the SSH
connection with the virtual machine, pass `COMMAND` instead. (e.g., `ssh vagrant@vm-ip COMMAND`)

- `--wait`: Instead of failing if no VM with the given name exists, wait for at most
`ssh-timeout` seconds. This is useful in scripts when starting a VM in the background
and connecting to it, as the VM will likely not be running by the time the shell executes
the `transient ssh` command.

### Examples

#### Connect to a Running Virtual Machine

```
$ transient ssh test-vm
alpine38:~$
```

#### Run a Command on a Running Virtual Machine

```
$ transient ssh test-vm --ssh-command "ls /"
bin
boot
dev
etc
home
lib
lost+found
media
mnt
proc
root
run
sbin
srv
sys
tmp
usr
var
```
