Feature: Configuration File
  In order to facilitate easier usage, prevent long argument strings, and
  promote consistent configuration sharing, Transient supports configuration
  files.

  Scenario: Invalid config file
    Given a transient run command
      And an http alpine disk image
      And the config file "invalid-config"
     When the transient command is run
     Then the return code is 1
      And stderr contains "ssh-foobar"

  Scenario: Run VM with a single SSH command
    Given a transient run command
      And an http alpine disk image
      And the config file "ssh-command-config"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "ssh-command working"

  Scenario: Multiple verbose flags are supported
    Given a transient create command
      And an http alpine disk image
      And the config file "multiple-verbose-flags-config"
      And a transient early flag "-vvv"
     When the transient command is run
     Then the return code is 0
      And stderr contains "INFO"
