Feature: Copy-in and Copy-out Support
    In order to facilitate easier file transfer between the host and guest,
    transient supports copy-in and copy-out support. Given a path on the host and an
    absolute path on the VM, transient can:
    - copy the host file or directory to the guest directory before starting the VM
    - copy the guest file or directory to the host directory after stopping the VM

  Scenario: Copy in a file before starting VM
    Given a transient vm
      And an http alpine disk image
      And a test file: "artifacts/copy-in-before-test-file"
      And a guest directory: "/home/vagrant/"
      And the test file is copied to the guest directory before starting
      And a ssh command "ls /home/vagrant"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "copy-in-before-test-file"

  Scenario: Copy in a large file before starting VM
    Given a transient vm
      And an http alpine disk image
      And a large test file: "artifacts/copy-in-large-test-file"
      And a guest directory: "/home/vagrant/"
      And the test file is copied to the guest directory before starting
      And a ssh command "ls /home/vagrant"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "copy-in-large-test-file"

  Scenario: Copy out a file after stopping VM
    Given a transient vm
      And an http alpine disk image
      And a host directory: "artifacts/"
      And a guest test file: "/home/vagrant/copy-out-after-test-file"
      And the guest test file is copied to the host directory after stopping
      And a ssh command "touch /home/vagrant/copy-out-after-test-file"
     When the vm runs to completion
     Then the return code is 0
      And the file "artifacts/copy-out-after-test-file" exists
