![Demo Gif](docs/assets/demo.gif)

transient
---------

[![Documentation Status](https://readthedocs.org/projects/transient/badge/?version=latest)](https://transient.readthedocs.io/en/latest/?badge=latest)

`transient` is thin wrapper for QEMU that provides additional features like downloading
disk images, shared folders, and SSH support. Currently `transient` only supports
[Vagrant](https://www.vagrantup.com/) libvirt images.

Installation
------------

`transient` is available on [PyPI](https://pypi.org/project/transient/), so the latest
release can be installed with `pip install transient`. To install `transient` from
source, clone this repository and run `pip install -e '.[dev]'` from the project
root. As always, the usage of python [virtual environments](https://docs.python.org/3/tutorial/venv.html)
is recommended for a development setup.

Documentation
-------------

Documentation for `transient` is available on [Read the Docs](https://transient.readthedocs.io/en/latest/).

Quick Start
-----------

`transient` is primarily a wrapper for QEMU. It supplies a small set of flags that
are used to add additional features to the VM being started. As the name implies,
it is almost completely stateless. This avoids problems that can sometimes occur
with `libvirt` based tools becoming 'unsynchronized' with the real system state.

For example, in the following command, the flags before the `--` are passed to
`transient`. The remaining arguments are passed directly to QEMU. This example
will cause `transient` to download and run a Centos7 VM (from the Vagrant Cloud)
with 1GB of memory using a text console. The `name` parameter is used to allow
subsequent invocations to use the same disk image, so changes will persist.

```
transient run \
   -name test-vm \
   -image centos/7:2004.01 \
   -- \
   -nographic -enable-kvm -m 1G
```

`transient` also supports a `vagrant` style SSH connection. This will start the
virtual machine and connect standard input and output to an SSH connection
with the machine, instead of the serial console. However, when this connection
is closed, the machine will be terminated (unlike `vagrant`). For example:

```
transient run \
   -name test-vm \
   -ssh-console \
   -image centos/7:2004.01 \
   -- \
   -enable-kvm -m 1G
```

The `-ssh-console` flag depends on the image having the normal vagrant keypair
trusted for the `vagrant` user.
