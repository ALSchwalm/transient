### Comprehensive Example

The following is a comprehensive configuration file found [here](https://github.com/ALSchwalm/transient/blob/master/test/config-files/comprehensive-config).

```
# A Transient config file

#
# Transient arguments are set in a similar manner compared to the command line.
# A few differences exist:
#
#   1. All values are set using an equal sign:
#
#          shutdown-timeout = 20
#
#
#   2. Strings are encapsulated with double quotes
#
#          name = "vm_name"
#
#
#   3. Flags are set to Booleans:
#
#          prepare-only = true
#          ssh-console = false
#
#
#   4. Lists are encapsulated by square brackets:
#
#          shared-folder = [
#              "/path/on/host:/path/on/guest",
#              "/path/on/host2:/path/on/guest2"
#          ]
#

[transient]

copy-in-before   = []
copy-out-after   = []
copy-timeout     = 0
image            = ["centos/7:2004.01"]
image_backend    = "$HOME/.local/share/transient/backend"
image_frontend   = "$HOME/.local/share/transient/frontend"
name             = "test-vm"
prepare-only     = true
qmp-timeout      = 10
shared-folder    = []
shutdown-timeout = 20
ssh-bin-name     = "/sbin/ssh"
ssh-command      = "whoami"
ssh-console      = false
ssh-port         = 1337
ssh-user         = "vagrant"
ssh-with-serial  = false


#
# QEMU arguments are set in a similar manner compared to the command line.
#
# The only difference is that the QEMU argument string is split by whitespace
# and encapsulated in a list.
#

[qemu]

qemu-args = [
    "-nographic",
    "-enable-kvm",
    "-m", "1G"
]
```
