Feature: Creating VMs
  In order to make it easier to run the same VM configuration multiple times,
  transient supports a 'create' subcommand that builds a VM state without
  running it.

  Scenario: Create with no name
    Given a transient create command
      And an http alpine disk image
     When the transient command is run
     Then the return code is 0

  Scenario: Create with a name can be used to start the VM
    Given a transient create command
      And an http alpine disk image
      And a name "test-create-vm"
      And a ssh console
      And a ssh command "echo create working"
     When the transient command is run
      And the return code is 0
      And a vm named "test-create-vm" is started
      And we wait for the vm to exit
     Then the return code is 0
     Then stdout contains "create working"

  Scenario: The same name cannot be created twice
    Given a transient create command
      And an http alpine disk image
      And a name "test-create-vm"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "already exists"

  Scenario: Flags passed at execution override creation flags
    Given a transient create command
      And an http alpine disk image
      And a name "test-create-vm-override"
      And a ssh console
      And a ssh command "echo nothing"
     When the transient command is run
      And the return code is 0
      And a vm named "test-create-vm-override" is started with flags "--ssh-command 'echo start working'"
      And we wait for the vm to exit
     Then the return code is 0
     Then stdout contains "start working"

  Scenario: Extra disks cannot be passed after creation
    Given a transient start command
      And a name "test-create-vm-override"
      And an extra argument "--extra-image generic/alpine38:v3.0.2"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "unrecognized arguments"
