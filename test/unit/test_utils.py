import pytest
import tempfile
import time

import transient.utils as u

# fmt: off
@pytest.mark.parametrize(
    [ 'default', 'entries', 'expected' ],
    [
        ( None,   ('y',),           True ),
        ( None,   ('Y',),           True ),
        ( None,   ('yes',),         True ),
        ( None,   ('YES',),         True ),
        ( None,   ('true',),        True ),
        ( None,   ('1',),           True ),

        ( None,   ('n',),           False ),
        ( None,   ('N',),           False ),
        ( None,   ('no',),          False ),
        ( None,   ('NO',),          False ),
        ( None,   ('false',),       False ),
        ( None,   ('0',),           False ),

        ( None,   ('', 'y'),        True ),
        ( None,   ('', 'f'),        False ),
        ( None,   ('a', 'b', 'y'),  True ),
        ( None,   ('a', 'b', 'f'),  False ),

        ( True,   ('y',),           True ),
        ( True,   ('n',),           False ),
        ( True,   ('',),            True ),
        ( True,   ('a', 'b', 'y'),  True ),
        ( True,   ('a', 'b', 'f'),  False ),
        ( True,   ('a', 'b', ''),   True ),

        ( False,  ('y',),           True ),
        ( False,  ('n',),           False ),
        ( False,  ('',),            False ),
        ( False,  ('a', 'b', 'y'),  True ),
        ( False,  ('a', 'b', 'f'),  False ),
        ( False,  ('a', 'b', ''),   False ),
    ],
    # function to make 'entries' part of the test name more legible
    ids=lambda arg: '/'.join(map(repr, arg)) if isinstance(arg, tuple) else None,
)
def test_prompt_yes_no(default, entries, expected, monkeypatch):
    entry = iter(entries)

    def mock_input(prompt):
        return next(entry)

    monkeypatch.setattr('builtins.input', mock_input)
    assert u.prompt_yes_no("test prompt", default) == expected

# fmt: on
def test_lock_file():
    with tempfile.NamedTemporaryFile() as f:
        with u.lock_file(f.name, "r", timeout=0) as locked:
            pass


def test_lock_file_unlocks():
    with tempfile.NamedTemporaryFile() as f:
        with u.lock_file(f.name, "r", timeout=0) as locked:
            pass

        # We should be able to get the lock again
        with u.lock_file(f.name, "r", timeout=0) as locked:
            pass


@pytest.mark.xfail(raises=OSError)
def test_lock_file_not_recursive():
    with tempfile.NamedTemporaryFile() as f:
        with u.lock_file(f.name, "r", timeout=0) as locked:
            with u.lock_file(f.name, "r", timeout=0) as second_lock:
                pass


def test_lock_file_timeout():
    with tempfile.NamedTemporaryFile() as f:
        with u.lock_file(f.name, "r", timeout=0) as locked:
            lock_timeout = 0.5
            start_time = time.time()
            try:
                with u.lock_file(f.name, "r", timeout=lock_timeout) as second_lock:
                    pass
            except OSError:
                assert time.time() - start_time >= lock_timeout
