Feature: Transient shows grace in the face of adversity

    In order to have a good user experience, Transient fails gracefully with a
    helpful message when it encounters an error.

    Scenario: Transient reports when a necessary program is missing
        This is most likely going to error out on qemu-image, but don't require
        that to pass.

        Given a transient vm
          And an http alpine disk image
          And environment variable PATH is set to ""
         When the transient command is run
         Then the return code is nonzero
          And stderr matches "Required program .* is not installed"

    Scenario: Transient reports when a necessary program produces binary garbage
        Given a transient vm
          And an http alpine disk image
          And environment variable PATH is set to "$PWD/resources/garbage-path:$PATH"
         When the transient command is run
         Then the return code is nonzero
          And stderr matches "Command produced garbage"

    Scenario: Transient reports when a necessary program cannot be run
        Don't append to $PATH below. Python is too clever when deciding which
        path entry has the correct qemu-img to run, and it will skip our bad
        one if it can.

        Given a transient vm
          And an http alpine disk image
          And environment variable PATH is set to "$PWD/resources/broken-path"
         When the transient command is run
         Then the return code is nonzero
          And stderr matches "Could not run required program .*: Permission denied"
