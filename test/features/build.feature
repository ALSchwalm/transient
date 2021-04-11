Feature: Image building
  In order to make building backend images simpler, transient supports
  an interface similar to dockerfiles

Scenario: Invalid Imagefile
    Given a transient build command
      And the prepare-build make target is run
      And an imagefile "resources/imagefiles/Imagefile.broken"
      And a build directory "artifacts/build-dir"
      And a name "broken"
     When the transient command is run
     Then the return code is 1
      And stderr contains "INVALID"

Scenario: Build alpine in build directory
    Given a transient build command
      And the prepare-build make target is run
      And an imagefile "resources/imagefiles/Imagefile.simple"
      And a build directory "artifacts/build-dir"
      And a name "test-build-alpine"
      And a transient flag "-local"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/build-dir/test-build-alpine.qcow2" exists

Scenario: Build alpine in backend
    Given a transient build command
      And the prepare-build make target is run
      And an imagefile "resources/imagefiles/Imagefile.alpine313"
      And a build directory "artifacts/build-dir"
      And a backend "./artifacts/test-backend"
      And a name "test-build-alpine-backend"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/test-backend/test%2Dbuild%2Dalpine%2Dbackend" exists

Scenario: The built image is usable
    Given a transient vm
      And a disk image "test-build-alpine-backend"
      And a backend "./artifacts/test-backend"
      And a ssh command "echo 'ssh-command working'"
     When the vm runs to completion
     Then the return code is 0
      And stdout contains "ssh-command working"

Scenario: Images can be built based on other images
    Given a transient build command
      And the prepare-build make target is run
      And an imagefile "resources/imagefiles/Imagefile.from_existing"
      And a build directory "artifacts/build-dir"
      And a backend "./artifacts/test-backend"
      And a name "test-build-alpine-existing"
     When the transient command is run
     Then the return code is 0
      And the file "artifacts/test-backend/test%2Dbuild%2Dalpine%2Dexisting" exists
