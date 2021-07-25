Feature: PS command
  In order to find other running (or non-running) transient instances, transient
  supports a 'ps' subcommand.

  Scenario: List other running instances
    Given a transient run command
      And an http alpine disk image
      And a ssh command "echo ---booted--- && sleep 600"
      And a ssh console
      And a name "ps-test-vm"
     When the vm runs
      And stdout contains "---booted---" within 30 seconds
      And a transient ps command runs
     Then the return code is 0
      And stdout contains "ps-test-vm"
      And the vm is terminated

  Scenario: List non-running vms
    Given a transient create command
      And an http alpine disk image
      And a name "ps-test-vm"
     When the transient command is run
      And a transient ps command runs with "--all"
     Then the return code is 0
      And stdout contains "ps-test-vm"
