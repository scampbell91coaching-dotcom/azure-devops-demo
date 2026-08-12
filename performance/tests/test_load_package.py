from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "k6" / "pl_beta.js").read_text()
README = (ROOT / "README.md").read_text()


def test_load_script_has_non_production_guard_and_write_opt_in():
    assert "PL_ALLOW_REMOTE" in SCRIPT
    assert "ENABLE_WRITES" in SCRIPT
    assert '"http://127.0.0.1:5000"' in SCRIPT
    assert "complete" not in SCRIPT.split("export function sessionProgress", 1)[1]


def test_priority_pl_workloads_and_thresholds_are_covered():
    for marker in (
        "/coach",
        "/athlete/programme/sessions/",
        "/programming/factory/preview",
        "/check-ins",
        "/nutrition",
        "/performance/charts",
        "/athlete/meal-plan",
    ):
        assert marker in SCRIPT
    for threshold in ("p(95)<750", "p(95)<500", "p(95)<2000", "rate<0.005"):
        assert threshold in SCRIPT
    assert "Meal-plan PDF export" in README

