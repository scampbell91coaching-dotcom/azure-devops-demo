from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_coach_base_has_dedicated_navigation():
    text = (ROOT / "templates" / "coach" / "base.html").read_text()

    assert "Traditional Strength Platform" in text
    assert "Coach Workspace" not in text
    assert 'href="/athletes"' in text
    assert "Programming" in text
    assert "Check-ins" in text
    assert "Meet Prep" in text


def test_athlete_pages_use_coach_base():
    athlete_templates = (
        ROOT / "templates" / "athletes" / name
        for name in ("dashboard.html", "list.html", "nutrition_checkin.html")
    )

    for template in athlete_templates:
        text = template.read_text()
        assert '{% extends "coach/base.html" %}' in text


def test_coach_base_does_not_use_operations_sidebar():
    text = (ROOT / "templates" / "coach" / "base.html").read_text().lower()

    assert "infrastructure" not in text
    assert "observability" not in text
    assert "resilience" not in text
    assert "recommendations" not in text


def test_coach_workspace_has_mobile_navigation():
    css = (ROOT / "static" / "css" / "coach_workspace.css").read_text()
    javascript = (ROOT / "static" / "js" / "coach_workspace.js").read_text()

    assert ".coach-menu-button" in css
    assert ".coach-navigation.is-open" in css
    assert 'classList.toggle("is-open")' in javascript
