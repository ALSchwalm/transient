from contextlib import contextmanager
import pytest
import tempfile

import transient.configuration
import transient.store
import transient.build


def imagefile_id_func(val):
    if not isinstance(val, str) or "\n" in val:
        return ""
    else:
        return val


@contextmanager
def does_not_raise():
    yield


@pytest.mark.parametrize(
    ("description", "contents", "expectation"),
    (
        (
            "Basic imagefile with only source",
            """
            FROM image_source
            """,
            does_not_raise(),
        ),
        (
            "Basic imagefile from scratch",
            """
            FROM scratch
            DISK 10Gb GPT
            PARTITION 0 MOUNT /
            """,
            does_not_raise(),
        ),
        ("Imagefile with no newline", "FROM image_source", does_not_raise()),
        (
            "Alpine imagefile",
            """
            FROM scratch
            DISK 2gb GPT
            PARTITION 1 SIZE 300MB FLAGS bios_grub
            PARTITION 2 FORMAT ext2 MOUNT /

            ADD alpine-3.13.tar.xz /
            """,
            does_not_raise(),
        ),
        (
            "Requires FROM",
            "",
            pytest.raises(RuntimeError, match="Exactly one FROM instruction must appear"),
        ),
        (
            "Only one FROM allowed",
            """
            FROM somesource
            FROM othersource
            """,
            pytest.raises(RuntimeError, match="Exactly one FROM instruction must appear"),
        ),
        (
            "FROM scratch requires disk",
            "FROM scratch",
            pytest.raises(
                RuntimeError, match="DISK.*must appear in images built from scratch"
            ),
        ),
        (
            "FROM scratch disk must have partition",
            """
            FROM scratch
            DISK 1GB GPT
            """,
            pytest.raises(
                RuntimeError, match="PARTITION.*must appear in images built from scratch"
            ),
        ),
        (
            "Some partition must mount at root",
            """
            FROM scratch
            DISK 1GB GPT
            PARTITION 0
            """,
            pytest.raises(RuntimeError, match="PARTITION.*must mount at /"),
        ),
        (
            "DISK can only be defined FROM scratch",
            """
            FROM someimage
            DISK 1GB GPT
            """,
            pytest.raises(
                RuntimeError,
                match="DISK and PARTITION.*can only appear on images built from scratch",
            ),
        ),
        (
            "FROM must appear first",
            """
            ADD foo /
            FROM someimage
            """,
            pytest.raises(
                RuntimeError,
                match="FROM instruction must appear before any other instructions",
            ),
        ),
        (
            "DISK must appear after FROM",
            """
            FROM scratch
            ADD foo /
            DISK 1GB GPT
            PARTITION 0 MOUNT /
            """,
            pytest.raises(
                RuntimeError,
                match="DISK instruction must appear immediately after FROM instruction",
            ),
        ),
        (
            "PARTITION must appear after DISK",
            """
            FROM scratch
            DISK 1GB GPT
            ADD foo /
            PARTITION 0 MOUNT /
            """,
            pytest.raises(
                RuntimeError,
                match="PARTITION instructions must appear immediately after DISK instruction",
            ),
        ),
    ),
    ids=imagefile_id_func,
)
def test_valid_imagefiles(description, contents, expectation):
    with expectation:
        with tempfile.TemporaryDirectory() as tempdir:
            with tempfile.NamedTemporaryFile() as imagefile:
                imagefile.write(contents.encode("utf8"))
                imagefile.flush()

                store = transient.store.BackendImageStore(path=tempdir)
                config = transient.configuration.create_transient_build_config(
                    {"file": imagefile.name}
                )

                builder = transient.build.ImageBuilder(config, store)
