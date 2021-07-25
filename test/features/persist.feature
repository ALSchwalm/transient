Feature: VM Persistence
  In order to support test/dev senarios where disk persistence is
  needed, transient can boot using the same disk multiple times.

  Scenario: Reboot a VM keeping changes
    Given a transient run command
      And a name "persist-test-vm"
      And a vmstore "./artifacts/test-vmstore"
      And an http alpine disk image
      And a ssh command "touch persist-is-working"
     When the vm runs to completion
      And a new ssh command "ls"
      And the vm runs to completion
     Then the return code is 0
      And stdout contains "persist-is-working"
