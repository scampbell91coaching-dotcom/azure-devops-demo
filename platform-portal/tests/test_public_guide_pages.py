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

    assert "Hip Pain Guide" in template
    assert "Shoulder Pain Guide" in template
    assert "Apply for Coaching" in template
    assert "About" not in template
    assert "Articles" not in template
    assert "Contact" not in template
