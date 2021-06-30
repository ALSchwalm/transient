Feature: SSH Console
  In order to support CI-style setups where the user wants to run only a
  single command (or only run commands once the system is known to be
  'fully' booted), transient supports using SSH as the VM connection

  Scenario: Run VM with a single SSH command
    Given a transient run command
      And an http alpine disk image
      And a ssh command "echo 'ssh-command working'"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "ssh-command working"

  Scenario: Run VM with a SSH console
    Given a transient run command
      And an http alpine disk image
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

  Scenario: Run VM with SSH and serial console
    Given a transient run command
      And an http alpine disk image
      And a ssh-with-serial console
     When the vm runs
      And the vm is provided stdin:
    """
    echo 'ssh-console working'
    exit
    """
      And we wait for the vm to exit
     Then the return code is 0
      And stdout contains "ssh-console working"
      And stdout contains "Linux version"
