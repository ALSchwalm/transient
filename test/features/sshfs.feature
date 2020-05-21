Feature: SSH Console
  In order to support conveniently moving data from the host to the guest
  (and vice versa), transient supports use sshfs to mount a host directory
  on the guest.

  @skip-in-ci
  Scenario: Run VM with a single SSHFS mount
    Given a transient vm
      And a name "test-vm"
      And a disk image "centos/7:2004.01"
      And a sshfs mount of "sync:/mnt"
      And a ssh command "ls /mnt"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "TEST_FOLDER_INDICATOR"
