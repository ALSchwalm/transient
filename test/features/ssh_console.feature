Feature: SSH Console
  In order to support CI-style setups where the user wants to run only a
  single command (or only run commands once the system is known to be
  'fully' booted), transient supports SSH-ing in to the VM.

  Scenario: Run VM with a single SSH command
    Given a transient vm
      And a name "test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And a ssh command "echo 'ssh-command working'"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "ssh-command working"

  Scenario: Run VM with a SSH console
    Given a transient vm
      And a name "test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And a ssh console
     When the vm runs
      And the vm is provided stdin:
        """
        echo 'ssh-console working'
        exit
        """
      And we wait for the vm to exit
     Then the return code is 0
      And stdout contains "ssh-console working"
