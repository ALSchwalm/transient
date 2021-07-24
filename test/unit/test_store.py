import pytest

import transient.utils
import transient.store as s

STORAGE_ENCODE_TESTS = (
    ("simple", "simple"),
    ("with space", "with%20space"),
    ("with-dash", "with%2Ddash"),
    ("with/slash", "with%2Fslash"),
)


@pytest.mark.parametrize(
    ("test_input", "expected"), STORAGE_ENCODE_TESTS,
)
def test_storage_safe_encode(test_input, expected):
    assert s.storage_safe_encode(test_input) == expected


@pytest.mark.parametrize(
    ("test_input", "expected"),
    [(test_out, test_in) for (test_in, test_out) in STORAGE_ENCODE_TESTS],
)
def test_storage_safe_decode(test_input, expected):
    assert s.storage_safe_decode(test_input) == expected


@pytest.mark.xfail(raises=transient.utils.TransientError)
def test_image_spec_unknown():
    s.ImageSpec("name,unknownspec=foobar")


@pytest.mark.xfail(raises=transient.utils.TransientError)
def test_image_spec_invalid():
    s.ImageSpec(",sometext")


def test_image_spec_implicit_vagrant():
    spec = s.ImageSpec("noproto")
    assert isinstance(spec.source_proto, s.VagrantImageProtocol)


def test_image_spec_vagrant():
    spec = s.ImageSpec("noproto,vagrant=centos/7:2004.01")
    assert isinstance(spec.source_proto, s.VagrantImageProtocol)


def test_image_spec_http():
    spec = s.ImageSpec(
        "noproto,http=https://github.com/ALSchwalm/transient-baseimages/releases/download/5/alpine-3.13.qcow2.xz"
    )
    assert isinstance(spec.source_proto, s.HttpImageProtocol)


def test_image_spec_file():
    spec = s.ImageSpec("noproto,file=/path/to/file")
    assert isinstance(spec.source_proto, s.FileImageProtocol)
