Feature: SSH Console
  In order to support conveniently moving data from the host to the guest
  (and vice versa), transient supports use sshfs to mount a host directory
  on the guest.

  Scenario: Install SSHFS on a CentOS VM
    Given a transient vm
      And a disk image "centos/7:2004.01"
      And a name "sshfs_test"
      And a ssh command "sudo yum install -y epel-release && sudo yum install -y sshfs"
     When the vm runs to completion
     Then the return code is 0

  Scenario: Run VM with a single SSHFS mount
    Given a transient vm
      And a disk image "centos/7:2004.01"
      And a name "sshfs_test"
      And a sshfs mount of "resources/sync:/mnt"
      And a ssh command "ls /mnt"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "TEST_FOLDER_INDICATOR"

  Scenario: Run VM with two SSHFS mounts
    Given a transient vm
      And a disk image "centos/7:2004.01"
      And a name "sshfs_test"
      And a sshfs mount of "resources/sync:/mnt"
      And a sshfs mount of "resources:/mnt2"
      And a ssh command "ls /mnt /mnt2"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "TEST_FOLDER_INDICATOR"
      And stdout contains "sync"
