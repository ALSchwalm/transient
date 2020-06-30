## Delete

The `delete` subcommand for `transient` provides a way to delete various images
in the Disk Frontend and Disk Backend.

### Usage

```
transient delete [-h] [-image IMG [IMG ...]] [-image-frontend IMAGE_FRONTEND]
                 [-image-backend IMAGE_BACKEND] [-name NAME] [-force]
```

- `-name NAME`: Find images associated with the provided `NAME`. Unlike the `run`
subcommand, this flag is not required for `delete`. It is possible to delete all VM
images associated with a given backend image by specifying only `-image` and not
`-name`, for example.

- `-image IMG [IMG ...]`: Delete images backed by the provided `IMG`. If no `-name`
is specified, information about the backend image itself is deleted

- `-image-frontend FRONTEND`: Use the provided `FRONTEND` path as the location to
find the per-VM image copies. Note: this path defaults to
`~/.local/share/transient/frontend`.

- `-image-backend BACKEND`: Use the provided `BACKEND` path as the location to
find the read-only backing images. Note: this path defaults to
`~/.local/share/transient/backend`.

- `-force`: Do not prompt yes/no before deletion

### Examples

#### Delete all images associated with a given VM name:
```
$ transient delete -name test-vm
The following images will be deleted:

Frontend Images:
┌─────────┬─────────────────────────┬──────────┬────────────┬───────────┐
│ VM Name │ Backend Image           │ Disk Num │  Real Size │ Virt Size │
├─────────┼─────────────────────────┼──────────┼────────────┼───────────┤
│ test-vm │ centos/7:2004.01        │        0 │ 110.57 MiB │ 40.00 GiB │
├─────────┼─────────────────────────┼──────────┼────────────┼───────────┤
│ test-vm │ generic/alpine38:v3.0.2 │        0 │   1.32 MiB │ 32.00 GiB │
└─────────┴─────────────────────────┴──────────┴────────────┴───────────┘
```

#### Delete the specified backend image

Note that this also deletes the frontend images that are backed by that image, as
they would no longer be functional after deleting the backend.
```
$ transient delete -image centos/7:2004.01
The following images will be deleted:

Frontend Images:
┌─────────┬──────────────────┬──────────┬────────────┬───────────┐
│ VM Name │ Backend Image    │ Disk Num │  Real Size │ Virt Size │
├─────────┼──────────────────┼──────────┼────────────┼───────────┤
│ test-vm │ centos/7:2004.01 │        0 │ 110.57 MiB │ 40.00 GiB │
└─────────┴──────────────────┴──────────┴────────────┴───────────┘

Backend Images:
┌──────────────────┬───────────┬───────────┐
│ Image Name       │ Real Size │ Virt Size │
├──────────────────┼───────────┼───────────┤
│ centos/7:2004.01 │  1.05 GiB │ 40.00 GiB │
└──────────────────┴───────────┴───────────┘
```

#### Delete images associated with a VM name and backed by a specific image
```
$ transient delete -image centos/7:2004.01 -name test-vm
The following images will be deleted:

Frontend Images:
┌─────────┬──────────────────┬──────────┬────────────┬───────────┐
│ VM Name │ Backend Image    │ Disk Num │  Real Size │ Virt Size │
├─────────┼──────────────────┼──────────┼────────────┼───────────┤
│ test-vm │ centos/7:2004.01 │        0 │ 110.57 MiB │ 40.00 GiB │
└─────────┴──────────────────┴──────────┴────────────┴───────────┘
```
