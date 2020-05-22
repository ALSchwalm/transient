Feature: Image Support
  In order to make it easier for a user to boot existing disk images,
  transient supports downloading Vagrant libvirt boxes. These can
  then be passed as disk images to QEMU

 Scenario: Download a single image
    Given a transient vm
      And a name "test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And the vm is prepare-only
     When the transient command is run
     Then the return code is 0

 Scenario: Set a custom frontend
    Given a transient vm
      And a name "test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And a frontend "./test-frontend"
      And the vm is prepare-only
     When the transient command is run
     Then the return code is 0
      And the file "test_vm-0-generic_alpine38_v3.0.2" is in the frontend

 Scenario: Set a custom backend
    Given a transient vm
      And a name "test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And a backend "./test-backend"
      And the vm is prepare-only
     When the transient command is run
     Then the return code is 0
      And the file "generic_alpine38_v3.0.2" is in the backend

 Scenario: Delete a frontend image
    Given a transient delete command
      And a name "test-vm"
      And a frontend "./test-frontend"
     When the transient command is run
     Then the return code is 0
      And the file "test_vm-0-generic_alpine38_v3.0.2" is not in the frontend

 Scenario: Delete a backend image
    Given a transient delete command
      And a disk image "generic/alpine38:v3.0.2"
      And a backend "./test-backend"
     When the transient command is run
     Then the return code is 0
      And the file "generic_alpine38_v3.0.2" is not in the backend