Feature: Image Support
  In order to make it easier for a user to boot existing disk images,
  transient supports downloading Vagrant libvirt boxes. These can
  then be passed as disk images to QEMU

  Scenario: Download a single image
    Given a transient create command
      And a disk image "generic/alpine38:v3.0.2"
     When the transient command is run
     Then the return code is 0

  Scenario: Download an uncompressed image via http
    Given a transient run command
      And a disk image "test_http_file,http=https://github.com/ALSchwalm/transient-baseimages/releases/download/4/alpine-3.13.qcow2"
      And a backend "./artifacts/test-backend"
      And a ssh command "echo passed"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "passed"

  Scenario: Download an image with the raw format
    Given a transient run command
      And a disk image "test_http_file_raw,http=https://github.com/ALSchwalm/transient-baseimages/releases/download/7/alpine-3.13.raw.xz"
      And a backend "./artifacts/test-backend"
      And a name "http_test_vm"
      And a ssh command "echo passed"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "passed"

  Scenario: Set a custom vmstore
    Given a transient create command
      And a name "image-test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And a vmstore "./artifacts/test-vmstore"
     When the transient command is run
     Then the return code is 0
      And the file "image%2Dtest%2Dvm/image%2Dtest%2Dvm-0-generic%2Falpine38%3Av3.0.2" is in the vmstore

  Scenario: Set a custom backend
    Given a transient create command
      And a disk image "generic/alpine38:v3.0.2"
      And a backend "./artifacts/test-backend"
     When the transient command is run
     Then the return code is 0
      And the file "generic%2Falpine38%3Av3.0.2" is in the backend

  Scenario: Delete a vm
    Given a transient rm command
      And a name "image-test-vm"
      And a vmstore "./artifacts/test-vmstore"
     When the transient command is run
     Then the return code is 0
      And the file "image%2Dtest%2Dvm/image%2Dtest%2Dvm-0-generic%2Falpine38%3Av3.0.2" is not in the vmstore

  Scenario: Use multiple image files
    Given a transient run command
      And a disk image "generic/alpine38:v3.0.2"
      And an extra disk image "generic/alpine38:v3.0.2"
      And a ssh command "ls /dev/sd*"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "sdb"

  Scenario: Use multiple image files without virtio-scsi
    Given a transient run command
      And a transient flag "--no-virtio-scsi"
      And a disk image "generic/alpine38:v3.0.2"
      And an extra disk image "generic/alpine38:v3.0.2"
      And a ssh command "ls /dev/sd*"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "sdb"

  Scenario: Connects image using virtio-scsi
    Given a transient run command
      And a disk image "generic/alpine38:v3.0.2"
      And a ssh command "ls -l /sys/block/sda"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "virtio"

  Scenario: Connect image with IDE
    Given a transient run command
      And a transient flag "--no-virtio-scsi"
      And a disk image "generic/alpine38:v3.0.2"
      And a ssh command "ls -l /sys/block/sda"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "ata"

  Scenario: Download a nonexistent image
    Given a transient create command
      And a disk image "djenerik/ahlpayn38:v3.0.2"
     When the transient command is run
     Then the return code is 1
      And there is no stack trace

  Scenario: Leave off a version specifier
    Given a transient create command
      And a disk image "generic/alpine38"
     When the transient command is run
     Then the return code is 1
      And there is no stack trace

  Scenario: Delete a backend image in use
    Given a transient image rm command
      And a disk image "generic/alpine38:v3.0.2"
      And a backend "./artifacts/test-backend"
     When the transient command is run
     Then the return code is nonzero
      And stderr contains "Backend 'generic/alpine38:v3.0.2' is in use by"

  Scenario: Delete a backend image forced
    Given a transient image rm command
      And an extra argument "--force"
      And a disk image "generic/alpine38:v3.0.2"
      And a backend "./artifacts/test-backend"
     When the transient command is run
     Then the return code is 0

  Scenario: Delete a nonexistent file
    Given a transient image rm command
      And a disk image "backend-does-not-exist"
      And a backend "./artifacts/test-backend"
     When the transient command is run
     Then the return code is 1
