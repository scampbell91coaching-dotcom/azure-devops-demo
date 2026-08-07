import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_guide_template_has_no_dashboard_sidebar():
    template = (ROOT / "templates" / "lead_magnet.html").read_text()

    assert "sidebar" not in template.lower()
    assert '{% extends "public/base.html" %}' in template


def test_both_guide_content_files_exist():
    content_dir = ROOT / "content" / "lead_magnets"

    for slug in ("hip-pain", "shoulder-pain"):
        path = content_dir / f"{slug}.json"
        data = json.loads(path.read_text())

        assert data["slug"] == slug
        assert len(data["steps"]) == 4
        assert data["coaching_url"]


def test_top_bar_contains_only_guides_and_apply_link():
    template = (ROOT / "templates" / "public" / "base.html").read_text()

    assert "Hip pain" in template
    assert "Shoulder pain" in template
    assert "Apply for coaching" in template
    assert "About" not in template
    assert "Articles" not in template
    assert "Contact" not in template


def test_public_header_has_logo_lockup_and_keyboard_menu_hooks():
    template = (ROOT / "templates" / "public" / "base.html").read_text()
    javascript = (ROOT / "static" / "js" / "public_guides.js").read_text()

    assert 'class="brand-lockup"' in template
    assert 'aria-controls="public-navigation"' in template
    assert 'data-public-menu' in template
    assert 'event.key === "Escape"' in javascript


def test_guides_use_honest_editorial_content_without_placeholders():
    component_dir = ROOT / "templates" / "public" / "components"
    text = "\n".join(path.read_text().lower() for path in component_dir.glob("*.html"))

    assert "photo placeholder" not in text
    assert "video placeholder" not in text
    assert "video goes here" not in text
