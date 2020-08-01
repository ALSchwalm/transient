## Configuration File Overview

In addition to configuring `transient` via the command line interface,
`transient` can also be configured via a configuration file.

Note that _only_ the `run` subcommand supports using a configuration file.

Every flag mentioned in [Run](../cli/run.md) can be set in a configuration file using the [TOML format](https://github.com/toml-lang/toml) .

For example, the command:

```
$ transient run \
   -name test-vm \
   -image centos/7:2004.01 \
   -- \
   -nographic -enable-kvm -m 1G
```

can be set in a configuration file as:

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

then executed with:

```
$ transient run -config transient-config.toml
```