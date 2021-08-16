## Getting Existing Images

`transient` supports a number of 'protocols' for retrieving backend images.
When the user specifies an image argument, the argument consists of three parts.
The image name, the protocol, and the source. So in this flag:
`myimage,http=https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud-20150628_01.qcow2`
The image name is 'myimage', the protocol is 'http' and the source is the
'cloud.centos.org' URL. When a transient command has been run with this
flag, the image will be retrieved using the given protocol, and stored
under the provided name in the backend.

The following image protocols are currently supported:

### Vagrant

The `vagrant` protocol retrieves a backend image from the Vagrant Cloud.
Currently only vagrant 'libvirt' boxes are supported. The `vagrant` protocol
'source' has two parts, the box name and the version. These must be separated
by a colon.For example, `myimage,vagrant=centos/7:2004.01` will download
the '2004.01' version of the 'centos/7' from the Vagrant Cloud and store it under
the name 'myimage'.

Note that the `vagrant` protocol is assumed if no explicit protocol is
supplied. So `centos/7:2004.01` is the same as
`centos/7:2004.01,vagrant=centos/7:2004.01`.

### HTTP

The `http` protocol will download the backend image from the provided
URL and store it under a given name. So for example
`myimage,http=https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud-20150628_01.qcow2`
will download the image from 'cloud.centos.org' and store it in the
backend as 'myimage'. Files compressed with `gzip`, `bzip2`, or `xz`
will be transparently decompressed when downloaded.

### File

The `file` protocol copies an existing file as a new backend image. For
example, `myimage,file=/path/to/image.qcow2` will copy file `image.qcow2`
to the backend with the name `myimage`. Files compressed with `gzip`, `bzip2`,
or `xz` will be transparently decompressed as they are copied.
