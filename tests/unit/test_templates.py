from lead_capture.domain.templates import placeholders, render


def test_placeholders_defaults_and_optional_parts():
    assert render("Hi[ {name}]!", {"name": "Priya"}) == "Hi Priya!"
    assert render("Hi[ {name}]!", {}) == "Hi!"
    assert render("{who|Student} is here", {}) == "Student is here"
    assert render("• {mode}[ — {area}, {city}]", {"mode": "Online", "area": "X"}) == "• Online"
    assert placeholders("{a} [{b|x}] {c}") == {"a", "b", "c"}
