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
    assert "coach_applications.index" in text
    assert "traditionalstrength.co.uk/apply" not in text
    assert "css/design-system.css" in text
    assert 'class="coach-workspace ts-theme-coach"' in text
    assert 'aria-label="Current workspace context"' in text
    assert "{% block coach_context %}" in text
    assert 'class="coach-navigation__divider" aria-hidden="true"' in text


def test_coach_workspace_uses_shared_foundation_without_dashboard_effects():
    css = (ROOT / "static" / "css" / "coach_workspace.css").read_text()

    assert "var(--ts-workspace-bg" in css
    assert "background: var(--coach-bg);" in css
    assert "radial-gradient" not in css
    assert "backdrop-filter" not in css


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


def test_coach_navigation_has_clear_active_and_persistent_context_styles():
    css = (ROOT / "static" / "css" / "coach_workspace.css").read_text()

    assert '.coach-navigation a[aria-current="page"]' in css
    assert "border-bottom-color: var(--coach-accent)" in css
    assert ".coach-context" in css
    assert "position: sticky" in css


def test_programming_context_persists_operational_hierarchy():
    session = (ROOT / "templates" / "programming" / "session.html").read_text()
    week = (ROOT / "templates" / "programming" / "week.html").read_text()

    for label in ("Athlete", "Block", "Week", "Session"):
        assert f"<b>{label}</b>" in session
    for label in ("Athlete", "Block", "Week"):
        assert f"<b>{label}</b>" in week
    assert 'class="programme-crumbs"' not in session
    assert 'class="programme-crumbs"' not in week
