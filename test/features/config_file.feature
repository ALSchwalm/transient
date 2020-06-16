Feature: Configuration File
  In order to facilitate easier usage, prevent long argument strings, and
  promote consistent configuration sharing, Transient supports configuration
  files.

Scenario: Invalid config file
   Given a transient vm
     And the config file "invalid-config"
    When the transient command is run
    Then the return code is 1
     And stderr contains "Invalid option on line"

Scenario: Run VM with a single SSH command
   Given a transient vm
     And the config file "ssh-command-config"
    When the vm runs to completion
    Then the return code is 0
     And stdout contains "ssh-command working"

Scenario: Multiple verbose flags are supported
   Given a transient vm
     And the config file "multiple-verbose-flags-config"
     And a transient early flag "-vvv"
    When the transient command is run
    Then the return code is 0
     And stderr contains "INFO"
