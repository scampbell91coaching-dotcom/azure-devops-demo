import json
from collections import Counter
from pathlib import Path

from portal.programming_templates import DAY_TEMPLATES


FIXTURE = Path(__file__).parent / "fixtures" / "programme_corpus_parity.v1.json"


def _load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _body(exposures):
    families = set(exposures)
    if families == {"bench"}:
        return "upper"
    if len(families) == 1:
        return "lower"
    return "full_body"


def test_golden_corpus_summary_is_reproducible():
    corpus = _load_fixture()
    sessions = corpus["sessions"]
    expected = corpus["expected"]

    accessory_counts = Counter(len(item["accessories"]) for item in sessions)
    slot_counts = Counter(
        item["primary_slots"] + item["secondary_slots"] for item in sessions
    )
    accessory_families = Counter(
        accessory["family"]
        for item in sessions
        for accessory in item["accessories"]
    )

    assert len(sessions) == expected["session_count"]
    assert dict(sorted(accessory_counts.items())) == {
        int(key): value
        for key, value in expected["accessory_count_distribution"].items()
    }
    assert [
        item["id"] for item in sessions if len(item["accessories"]) > 3
    ] == expected["sessions_over_three_accessories"]
    assert dict(sorted(slot_counts.items())) == {
        int(key): value for key, value in expected["slot_count_distribution"].items()
    }
    assert sum(item["secondary_slots"] for item in sessions) == expected[
        "secondary_slot_count"
    ]
    assert Counter(_body(item["exposures"]) for item in sessions) == expected[
        "body_distribution"
    ]
    assert accessory_families == expected["repeated_accessory_families"]


def test_golden_static_template_rows_match_the_maintained_source():
    corpus = _load_fixture()
    static = {
        item["id"].removeprefix("static-"): item
        for item in corpus["sessions"]
        if item["id"].startswith("static-")
    }

    assert set(static) == set(DAY_TEMPLATES)
    for code, template in DAY_TEMPLATES.items():
        item = static[code]
        assert item["primary_slots"] == len(template["exercises"])
        assert item["accessories"] == []
        assert item["patterns"] == [
            f"{sets}x{reps}@{rpe}"
            for _, sets, reps, rpe in template["exercises"]
        ]


def test_parity_policy_retains_authoritative_zero_and_manual_modes():
    corpus = _load_fixture()
    policy = corpus["parity_policy"]
    observed_over_three = corpus["expected"]["sessions_over_three_accessories"]

    assert policy["automatic_accessory_maxima"] == {
        "low": 1,
        "medium": 2,
        "high": 3,
    }
    assert observed_over_three == []
    assert policy["raise_high_cap_only_when_observed_session_count_over_three_is_positive"]
    assert policy["manual_pins_replace_automatic"]
    assert policy["manual_pin_order_is_authoritative"]
    assert policy["explicit_no_assistance_count"] == 0
