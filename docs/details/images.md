## Getting Images

`transient` supports a number of 'protocols' for retrieving backend images.
When the user uses the `-image` flag, the argument consists of three parts.
The image name, the protocol, and the source. So in this flag:
`-image myimage,http=https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud-20150628_01.qcow2`
The image name is 'myimage', the protocol is 'http' and the source is the
'cloud.centos.org' url. When a transient command has been run with this
flag, the image will be retrieved using the given protocol, and stored
under the provided name in the backend.

The following image protocols are currently supports:

### Vagrant

The `vagrant` protocol retrieves a backend image from the Vagrant Cloud.
Currently only vagrant 'libvirt' boxes are supported. The `vagrant` protocol
'source' has two parts, the box name and the version. These must be separated
by a colon.For example, `-image myimage,vagrant=centos/7:2004.01` will download
the '2004.01' version of the 'centos/7' from the Vagrant Cloud and store it under
the name 'myimage'.

Note that the `vagrant` protocol is assumed if no explicit protocol is
supplied. So `-image centos/7:2004.01` is the same as
`-image centos/7:2004.01,vagrant=centos/7:2004.01`.

### HTTP

The `http` protocol will download the backend image from the provided
URL and store it under a given name. So for example
`-image myimage,http=https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud-20150628_01.qcow2`
will download the image from 'cloud.centos.org' and store it in the
backend as 'myimage'.

### Frontend

The `frontend` protocol is used to build a backend image from some
existing frontend image. This is useful when an initial 'provisioning'
step is needed to configure an image that has been retrieved from a
different protocol.

For example, after first running:

`transient run -name provisioned -image mybaseimage,vagrant=centos/7:2004.01 -ssh`

A subsequent command could be used to build a backend image from the
frontend image created by the above command:

`transient run -name test-vm -image mytestimage,frontend=provisioned@mybaseimage -ssh`

So the protocol here is `frontend` and the source is `provisioned@mybaseimage`.
For the `frontend` protocol, the source has two parts: the VM name and the
backend image name for the frontend disk that will be copied to the backend.
