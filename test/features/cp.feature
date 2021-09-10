Feature: Copy files to or from an offline VM disk
  In order to support easy inspection of a VM image, transient should support
  copying files to/from a VM without starting the VM (e.g., without needing
  to run with '--copy-in-before' or '--copy-out-after')

  Scenario: Create VM for CP copy testing
    Given a transient create command
      And an http alpine disk image
      And a name "test-cp-vm"
      And a ssh console
     When the transient command is run
     Then the return code is 0

  Scenario: Attempt to copy without specifying a VM
    Given a transient cp command
      And an argument "/path"
      And an argument "/path"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "must be VM paths"

  Scenario: Attempt to copy to a nonexistent VM
    Given a transient cp command
      And an argument "noexist:/path"
      And an argument "/path"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "No VM with name 'noexist'"

  Scenario: Attempt to copy a nonexistent file
    Given a transient cp command
      And an argument "/file/noexist"
      And an argument "test-cp-vm:/"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "No such file or directory"

  Scenario: Copy a file to an existing VM
    Given a transient cp command
      And a test file: "artifacts/cp-test-file"
      And an argument "artifacts/cp-test-file"
      And an argument "test-cp-vm:/"
     When the transient command is run
      And the return code is 0
      And a vm named "test-cp-vm" is started with flags "--ssh-command 'ls /'"
      And we wait for the vm to exit
     Then the return code is 0
      And stdout contains "cp-test-file"

  Scenario: Copy a file from an existing VM
    Given a transient cp command
      And an argument "test-cp-vm:/etc/os-release"
      And an argument "artifacts/cp-os-release"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/cp-os-release" exists
