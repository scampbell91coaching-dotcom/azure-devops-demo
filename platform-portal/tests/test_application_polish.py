from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_honeypot_is_hidden_by_application_styles():
    css = (ROOT / "static" / "css" / "coaching_application.css").read_text()

    assert ".honeypot" in css
    assert "left: -10000px" in css


def test_save_message_only_becomes_visible_after_activity():
    css = (ROOT / "static" / "css" / "coaching_application.css").read_text()
    javascript = (ROOT / "static" / "js" / "coaching_application.js").read_text()

    assert ".save-note.is-visible" in css
    assert 'classList.add("is-visible")' in javascript
    assert 'classList.remove("is-visible")' in javascript


def test_application_layout_is_centred():
    css = (ROOT / "static" / "css" / "coaching_application.css").read_text()

    assert ".wizard-shell" in css
    assert "margin-inline: auto" in css
    assert ".wizard-step__heading" in css
    assert "text-align: center" in css


def test_mobile_layout_stacks_fields_and_buttons():
    css = (ROOT / "static" / "css" / "coaching_application.css").read_text()

    assert "@media (max-width: 760px)" in css
    assert ".editorial-grid--three" in css
    assert "grid-template-columns: 1fr" in css
