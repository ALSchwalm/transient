## Build

The `build` subcommand for `transient` allows the user to easily build
virtual machine disk images using a simple declarative format similar to
the well-known Dockerfile format. This format is described on the
[Imagefile Format page](../images/format.md). Additional information about
the image building process and architecture can be found on the
[Building Images page](../images/building.md).

### Usage

```
transient build -name NAME [-h] [-local] [-file IMAGEFILE]
                [-image-backend IMAGE_BACKEND] BUILD_DIR
```

- `-name NAME`: Associate the new image with the provided `NAME`. For `-local`
builds, the image is stored as `<NAME>.qcow2` in the `BUILD_DIR`. For non-`local`
builds, the `NAME` is used as the backend name.

- `-local`: Store the built image in the `BUILD_DIR` instead of the `IMAGE_BACKEND`.

- `-file`: Use the specified `IMAGEFILE` instead of the default `<BUILDDIR>/Imagefile`.

- `-image-backend BACKEND`: Use the provided `BACKEND` path as the location to store
the built image

- `BUILDDIR`: The build directory is the root directory when refering to relative paths
from the Imagefile.

### Examples

#### Build a VM image based on Centos 7

Given a simple `Imagefile` with the following contents:

```
FROM centos/7:2004.01
RUN yum install -y nano
RUN echo 'myhostname' > /etc/hostname
```

Then if we run the following:

```
$ transient build -name example build_dir/
Step 1/3 : FROM centos/7:2004.01
100% |##############################################|   1.7 GiB/s |   1.1 GiB | Time:  0:00:00
Step 2/3 : RUN yum install -y nano
Loaded plugins: fastestmirror
Determining fastest mirrors
 * base: reflector.westga.edu
 * extras: repos.hou.layerhost.com
 * updates: yum.tamu.edu
Resolving Dependencies
--> Running transaction check
---> Package nano.x86_64 0:2.3.1-10.el7 will be installed
--> Finished Dependency Resolution

Dependencies Resolved

================================================================================
 Package        Arch             Version                   Repository      Size
================================================================================
Installing:
 nano           x86_64           2.3.1-10.el7              base           440 k

Transaction Summary
================================================================================
Install  1 Package

Total download size: 440 k
Installed size: 1.6 M
Downloading packages:
warning: /var/cache/yum/x86_64/7/base/packages/nano-2.3.1-10.el7.x86_64.rpm: Header V3 RSA/SHA256 Signature, key ID f4a80eb5: NOKEY
Public key for nano-2.3.1-10.el7.x86_64.rpm is not installed
Retrieving key from file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
Importing GPG key 0xF4A80EB5:
 Userid     : "CentOS-7 Key (CentOS 7 Official Signing Key) <security@centos.org>"
 Fingerprint: 6341 ab27 53d7 8a78 a7c2 7bb1 24c6 a8a7 f4a8 0eb5
 Package    : centos-release-7-8.2003.0.el7.centos.x86_64 (@anaconda)
 From       : /etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
Running transaction check
Running transaction test
Transaction test succeeded
Running transaction
  Installing : nano-2.3.1-10.el7.x86_64                                     1/1
warning: %post(nano-2.3.1-10.el7.x86_64) scriptlet failed, exit status 127
Non-fatal POSTIN scriptlet failure in rpm package nano-2.3.1-10.el7.x86_64
  Verifying  : nano-2.3.1-10.el7.x86_64                                     1/1

Installed:
  nano.x86_64 0:2.3.1-10.el7

Complete!
Step 3/3 : RUN echo 'myhostname' > /etc/hostname
```

Then a new image named `example` will exist in the backend. A virtual machine using
this backend can be started as usual:

```
$ transient run -image example -cmd hostname -- -enable-kvm -m 1G
Finished preparation. Starting virtual machine
myhostname
```