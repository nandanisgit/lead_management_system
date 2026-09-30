"""The phone_number field type (FR-032): accepted forms and normalisation."""

from datetime import date

import pytest

from lead_capture.domain.field_types import InvalidValue, normalise

TODAY = date(2026, 9, 30)


def phone_spec(schema):
    [name] = schema.channel_phone_fields()
    return schema.fields[name]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9876543210", "+919876543210"),
        ("98765 43210", "+919876543210"),
        ("+91 98765-43210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("(+91) 98765.43210", "+919876543210"),
        ("+1 415 555 2671", "+14155552671"),
        ("0044 20 7946 0958", "+442079460958"),
    ],
)
def test_accepted_forms(schema, raw, expected):
    assert normalise(phone_spec(schema), raw, schema, TODAY) == expected


@pytest.mark.parametrize("raw", ["12345", "call me", "+91 12345", "98765432101234567", ""])
def test_rejected(schema, raw):
    with pytest.raises(InvalidValue):
        normalise(phone_spec(schema), raw, schema, TODAY)


def test_phone_field_is_private(schema):
    assert set(schema.channel_phone_fields()) <= schema.pii_fields()
