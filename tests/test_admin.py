"""Tests for admin.py passcode checks."""

from admin import check_passcode


def test_correct_passcode():
    assert check_passcode("sesame-street-42", "sesame-street-42")


def test_wrong_or_empty_passcode():
    assert not check_passcode("sesame", "sesame-street-42")
    assert not check_passcode("", "sesame-street-42")


def test_no_passcode_configured_fails_closed():
    assert not check_passcode("anything", None)
    assert not check_passcode("", "")
