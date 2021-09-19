## Configuration File Format

In addition to configuration via the command line interface, `transient`
can also be configured via a configuration file. Flags mentioned in
[create/run/start/stop](../../cli/run_create_start_stop/) can be set in a
configuration file using the [TOML format](https://github.com/toml-lang/toml).
Currently, only the `run`, `start` and `create` subcommands supports using
a configuration file.

For example, consider the following command:

```bash
$ transient run generic/alpine38:v3.0.2 \
   --name test-vm \
   --ssh-console \
   -- \
   -nographic -enable-kvm -m 1G
```

The following `transient` configuration file would produce the same behavior when
executed:

```
# transient-config.toml

name = "test-vm"
ssh-console = true
qemu-args = [
    "-nographic",
    "-enable-kvm",
    "-m", "1G"
]
```

_NOTE: required parameters like the image (in this example, `generic/alpine38:v3.0.2`)
cannot currently be specified via the config file._

A `transient` configuration can be supplied using the `--config` flag. For example:

```
$ transient run generic/alpine38:v3.0.2 --config transient-config.toml
```
