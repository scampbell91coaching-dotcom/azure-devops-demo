from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_application_template_uses_wizard_steps():
    text = (ROOT / "templates" / "public" / "coaching_application.html").read_text()

    assert 'data-step="1"' in text
    assert 'data-step="5"' in text
    assert "Review Application" in text
    assert "Submit Application" in text


def test_application_template_does_not_mention_current_coach():
    text = (
        (ROOT / "templates" / "public" / "coaching_application.html")
        .read_text()
        .lower()
    )

    assert "current coach" not in text
    assert "who coaching is not for" not in text


def test_application_wizard_saves_browser_progress():
    text = (ROOT / "static" / "js" / "coaching_application.js").read_text()

    assert "localStorage.setItem" in text
    assert "localStorage.getItem" in text
    assert "traditional-strength-coaching-application" in text


def test_application_has_no_photo_placeholders():
    text = (
        (ROOT / "templates" / "public" / "coaching_application.html")
        .read_text()
        .lower()
    )

    assert "photo placeholder" not in text
    assert "<img" not in text
