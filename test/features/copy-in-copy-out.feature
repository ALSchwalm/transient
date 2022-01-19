Feature: Copy-in and Copy-out Support
  In order to facilitate easier file transfer between the host and guest,
  transient supports copy-in and copy-out support. Given a path on the host and an
  absolute path on the VM, transient can:
  - copy the host file or directory to the guest directory before starting the VM
  - copy the guest file or directory to the host directory after stopping the VM

  Scenario Outline: Copy in a file before starting VM
    Given a transient run command
      And an http alpine disk image
      And a test file: "artifacts/copy-in-before-test-file"
      And a guest directory: "/home/vagrant/"
      And the test file is copied to the guest directory before starting
      And using the "<image_type>" image for copying
      And a ssh command "ls /home/vagrant"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "copy-in-before-test-file"

    Examples: Image Types
      | image_type |
      | dedicated  |
      | same       |

  Scenario Outline: Copy in a large file before starting VM
    Given a transient run command
      And an http alpine disk image
      And a large test file: "artifacts/copy-in-large-test-file"
      And a guest directory: "/home/vagrant/"
      And the test file is copied to the guest directory before starting
      And using the "<image_type>" image for copying
      And a ssh command "ls /home/vagrant"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "copy-in-large-test-file"

    Examples: Image Types
      | image_type |
      | dedicated  |
      | same       |

  Scenario Outline: Copy out a file after stopping VM
    Given a transient run command
      And an http alpine disk image
      And a host directory: "artifacts/"
      And a guest test file: "/home/vagrant/copy-out-after-test-file"
      And the guest test file is copied to the host directory after stopping
      And using the "<image_type>" image for copying
      And a ssh command "touch /home/vagrant/copy-out-after-test-file"
     When the vm runs to completion
     Then the return code is 0
      And the file "artifacts/copy-out-after-test-file" exists

    Examples: Image Types
      | image_type |
      | dedicated  |
      | same       |

  Scenario Outline: Copy out a file after stopping VM using rsync
    Given a transient run command
      And an http alpine disk image
      And a host directory: "artifacts/"
      And a guest test file: "/home/vagrant/copy-out-after-test-file"
      And the guest test file is copied to the host directory after stopping
      And using the "<image_type>" image for copying
      And a ssh command "touch /home/vagrant/copy-out-after-test-file"
      And an extra argument "--rsync"
     When the vm runs to completion
     Then the return code is 0
      And the file "artifacts/copy-out-after-test-file" exists

    Examples: Image Types
      | image_type |
      | dedicated  |
      | same       |

  Scenario Outline: Copy in a symbolic link using rsync
    Given a transient run command
      And an http alpine disk image
      And a symbolic link "artifacts/symlink" to "/etc/hostname"
      And a guest directory: "/home/vagrant/"
      And the test file is copied to the guest directory before starting
      And using the "<image_type>" image for copying
      And a ssh command "test -L /home/vagrant/symlink"
      And an extra argument "--rsync"
     When the vm runs to completion
     Then the return code is 0

    Examples: Image Types
      | image_type |
      | dedicated  |
      | same       |
