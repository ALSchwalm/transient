Feature: Command line interface
  In order to use transient, users can access the command line interface.

  Scenario: Missing subcommand
    Given a transient command
     When the transient command is run
     Then the return code is 0
      And stdout contains "usage:"

  Scenario: Invalid flag
    Given a transient run command
      And an http alpine disk image
      And a transient flag "--ssh-foobar"
     When the transient command is run
     Then the return code is 2
      And stderr contains "error: unrecognized arguments: --ssh-foobar"

  Scenario: QEMU fast exit without error
    Given a transient run command
      And an http alpine disk image
      And a qemu flag "-version"
     When the transient command is run
     Then the return code is 0
      And stdout contains "QEMU emulator version"

  Scenario: Multiple verbose flags is supported
    Given a transient create command
      And an http alpine disk image
      And a transient early flag "-vvv"
     When the transient command is run
     Then the return code is 0
      And stderr contains "INFO"

  Scenario: Verbose flags work when added after subcommand
    Given a transient create command
      And an http alpine disk image
      And a transient flag "-vvv"
     When the transient command is run
     Then the return code is 0
      And stderr contains "INFO"
