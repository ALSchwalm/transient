Feature: SSH Command
  In order to support test cases where multiple commands must be run
  on a single VM (and failure or output captured), transient supports
  an SSH command to connect to a running VM. This requires that the
  VM was started with the `-ssh-console` flag.

  Scenario: Run an SSH command on a running VM
    Given a transient run command
      And a disk image "generic/alpine38:v3.0.2"
      And a ssh command "sleep 600"
      And a ssh console
      And a name "test-vm"
     When the vm runs
      And a transient ssh command "echo ssh-command working" runs on "test-vm" with "--wait"
     Then the return code is 0
      And stdout contains "ssh-command working"
      And the vm is terminated

  Scenario: Attempt to connect to a VM that is not running
     When a transient ssh command "echo ssh-command working" runs on "test-vm"
     Then the return code is 1
      And stderr contains "No running VM"

  Scenario: Run ssh with custom options
    Given a transient run command
      And a disk image "generic/alpine38:v3.0.2"
      And a ssh command "sleep 600"
      And a ssh console
      And a name "test-vm"
      And an extra argument "--ssh-option ControlMaster=yes"
      And an extra argument "--ssh-option ControlPath=myctrlsock"
     When the vm runs
     Then the file "myctrlsock" appears within 180 seconds
      And "myctrlsock" is a socket
      And the vm is terminated
