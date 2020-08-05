## Configuration File Overview

In addition to configuration via the command line interface, `transient`
can also be configured via a configuration file. Every flag mentioned in
[Run](../cli/run.md) can be set in a configuration file using the
[TOML format](https://github.com/toml-lang/toml). Note that _only_ the
`run` subcommand supports using a configuration file.

For example, consider the following command:

```
$ transient run \
   -name test-vm \
   -image centos/7:2004.01 \
   -- \
   -nographic -enable-kvm -m 1G
```

The following `transient` configuration file would produce the same behavior when
executed:

```
# transient-config.toml

[transient]

name = "test-vm"
image = ["centos/7:2004.01"]

[qemu]

qemu-args = [
    "-nographic",
    "-enable-kvm",
    "-m", "1G"
]
```

A `transient` configuration can be supplied to the `run` command using the
`-config` flag. For example:

```
$ transient run -config transient-config.toml
```

For a more complete example of a `transient` configuration file, see the
[Comprehensive Example page](./comprehensive-example.md).