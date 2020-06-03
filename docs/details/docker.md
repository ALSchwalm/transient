## Running Under Docker

`transient` generally supports execution under Docker (or other container solutions),
with the following exceptions:

- Shared Folders: Because shared folder support in `transient` uses SSHFS from the
guest to the host, there is no way convenient way to use them with Docker. The
container would need to be running an SSH server and have the relevant ports
forwarded in order to potentially do this. This setup is not 'officially' supported
with `transient`.

- Copy In/Out: The `-copy-in-before` and `-copy-out-after` flags depend on using
libguestfs. This is functional under docker, but due to a bug the directory
`/lib/modules` must exist. This can be an empty directory, but it must exist for
libguestfs to function properly.
