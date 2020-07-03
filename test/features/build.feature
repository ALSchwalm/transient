Feature: Image building
  In order to make building backend images simpler, transient supports
  an interface similar to dockerfiles

Scenario: Invalid Imagefile
    Given a transient build command
      And an imagefile "resources/imagefiles/Imagefile.broken"
      And a build directory "artifacts/build-dir"
      And a name "broken"
     When the transient command is run
     Then the return code is 1
      And stderr contains "INVALID"

Scenario: Build ubuntu in build directory
    Given a transient build command
      And an imagefile "resources/imagefiles/Imagefile.simple"
      And a build directory "artifacts/build-dir"
      And a name "test-build-ubuntu"
      And a transient flag "-local"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/build-dir/test-build-ubuntu.qcow2" exists

Scenario: Build ubuntu in backend
    Given a transient build command
      And an imagefile "resources/imagefiles/Imagefile.ubuntu"
      And a build directory "artifacts/build-dir"
      And a backend "./artifacts/test-backend"
      And a name "test-build-ubuntu-backend"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/test-backend/test%2Dbuild%2Dubuntu%2Dbackend" exists

Scenario: The built image is usable
    Given a transient vm
      And a disk image "test-build-ubuntu-backend"
      And a backend "./artifacts/test-backend"
      And a ssh command "echo 'ssh-command working'"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "ssh-command working"

Scenario: Images can be built based on other images
    Given a transient build command
      And an imagefile "resources/imagefiles/Imagefile.from_existing"
      And a build directory "artifacts/build-dir"
      And a backend "./artifacts/test-backend"
      And a name "test-build-centos-existing"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/test-backend/test%2Dbuild%2Dcentos%2Dexisting" exists
