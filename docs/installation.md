## Installation

`transient` is available on [PyPI](https://pypi.org/), so it can be installed by
running `pip install transient`. Additionally it may be installed from
[GNU Guix](https://guix.gnu.org), and can be installed by running
`guix install python-transient`. Currently `transient` supports the following
minimum versions of QEMU and python:

- Python 3.6
- QEMU 2.11

Other versions may work, but are not tested. The standard test platform for
`transient` is Ubuntu 18.04. On Ubuntu, the following packages provide compatible
versions of the `transient` dependencies:

`apt-get install ssh qemu-system-x86 python3-pip`

`transient` has an optional dependency on [rsync](https://rsync.samba.org/), which
can be used for copying files to/from a virtual machine. `rsync` can be installed
on ubuntu with:

`apt-get install rsync`