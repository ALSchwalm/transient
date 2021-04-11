Feature: Command line interface
  In order to use transient, users can access the command line interface.

Scenario: Invalid flag
    Given a transient vm
      And an http alpine disk image
      And a transient flag "-ssh-foobar"
     When the transient command is run
     Then the return code is 2
      And stderr contains "Error: no such option: -ssh-foobar"

Scenario: QEMU fast exit without error
    Given a transient vm
      And an http alpine disk image
      And a qemu flag "-version"
     When the transient command is run
     Then the return code is 0
      And stdout contains "QEMU emulator version"

Scenario: Multiple verbose flags is supported
    Given a transient vm
      And an http alpine disk image
      And a transient early flag "-vvv"
      And the vm is prepare-only
     When the transient command is run
     Then the return code is 0
      And stderr contains "INFO"

Scenario: Transient is run with no qemu arguments
    Given a transient vm with no qemu arguments
      And the vm is prepare-only
     When the transient command is run
     Then the return code is 0
