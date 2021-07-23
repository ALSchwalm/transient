Feature: Commit VM changes to a new image
  In order to support a pre-test provisioning step, it is useful to be able
  to create a new backend image including the changes made by some VM. This
  is supported by the 'commit' feature.

  Scenario: Commiting a nonexistent VM fails
    Given a transient commit command
      And a vm name "does-not-exist"
      And a name "newimage"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "No VM with name"

  Scenario: Committing creates a new image
    Given a transient run command
      And an http alpine disk image
      And a name "commit-test-vm"
      And a ssh command "sudo touch /test-passing"
     When the transient command is run
      And the return code is 0
      And changes to "commit-test-vm" are commited as "commit-test-image-new"
     Then the return code is 0

  Scenario: The same name cannot be committed twice
    Given a transient commit command
      And a vm name "commit-test-vm"
      And a name "commit-test-image-new"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "already exists"

  Scenario: Commited changes are reflected in the new image
    Given a transient run command
      And a disk image "commit-test-image-new"
      And a ssh command "test -f /test-passing"
     When the vm runs to completion
     Then the return code is 0
