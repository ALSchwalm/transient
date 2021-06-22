import pytest
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
# fmt: on
def test_prompt_yes_no(default, entries, expected, monkeypatch):
    entry = iter(entries)

    def mock_input(prompt):
        return next(entry)

    monkeypatch.setattr('builtins.input', mock_input)
    assert u.prompt_yes_no("test prompt", default) == expected
