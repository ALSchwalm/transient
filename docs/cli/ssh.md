## SSH

The `ssh` subcommand for `transient` allows a user to connect to a running
`transient` virtual machine by name.

### Usage

```
transient ssh -name NAME [-ssh-user USER] [-ssh-timeout TIMEOUT] [-ssh-bin-name NAME]
                         [-ssh-command COMMAND]
```

- `-name NAME`: The name of the `transient` virtual machine to connect to

- `-ssh-timeout TIMEOUT`: Wait `TIMEOUT` seconds when attempting to make an SSH
connection with the virtual machine before failing. Defaults to 90 seconds.

- `-ssh-user USER`: Pass `USER` as the username when making an SSH connection to the
virtual machine.

- `-ssh-bin-name NAME`: Use `NAME` as the command instead of `ssh` when making an
SSH connection with the virtual machine.

- `-ssh-command COMMAND`: Instead of connecting standard input and output to the SSH
connection with the virtual machine, pass `COMMAND` instead. (e.g., `ssh vagrant@vm-ip COMMAND`)

### Examples

#### Connect to a Running Virtual Machine

```
$ transient ssh -name test-vm
alpine38:~$
```

#### Run a Command on a Running Virtual Machine

```
$ transient ssh -name test-vm -ssh-command "ls /"
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
