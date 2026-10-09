"""Tests for qa_discover.py CLI arg handling (QA-BUNKER-48).

Regression coverage for:
- `--help` must print usage and exit 0 (was: ValueError traceback from
  int() on sys.argv[1] before any parsing).
- Negative / zero N must be rejected with a one-line stderr error and a
  nonzero exit, never dumping the whole fleet.
- Positive N and the no-arg default are unchanged.
"""
import pytest

import qa_discover


def test_default_n_is_2_when_no_args():
    args = qa_discover.parse_args([])
    assert args.n == 2


def test_positive_n_accepted():
    assert qa_discover.parse_args(['5']).n == 5
    assert qa_discover.parse_args(['1']).n == 1


def test_help_exits_zero_with_usage(capsys):
    with pytest.raises(SystemExit) as exc:
        qa_discover.parse_args(['--help'])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'usage:' in out
    assert 'N' in out
    assert 'projects that need a full CI pass' in out


def test_negative_n_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        qa_discover.parse_args(['-3'])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert 'positive integer' in err
    assert '-3' in err


def test_zero_n_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        qa_discover.parse_args(['0'])
    assert exc.value.code != 0
    assert 'positive integer' in capsys.readouterr().err


def test_non_integer_n_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        qa_discover.parse_args(['abc'])
    assert exc.value.code != 0
    assert 'integer' in capsys.readouterr().err


def test_positive_int_type_boundary():
    assert qa_discover.positive_int('7') == 7
    with pytest.raises(Exception):
        qa_discover.positive_int('-1')
