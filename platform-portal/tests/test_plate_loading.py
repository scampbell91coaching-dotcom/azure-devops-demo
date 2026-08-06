from decimal import Decimal

import pytest

from portal.services.plate_loading import build_warmups, calculate_load, default_inventory


@pytest.mark.parametrize(
    ("target", "bar", "collars"),
    [(20, 20, 0), (100, 20, 0), (202.5, 20, 0), (60, 15, 0), (105, 20, 5), (50.5, 20, 0)],
)
def test_common_light_heavy_bars_collars_and_microplate_totals(target, bar, collars):
    result = calculate_load(target, bar_kg=bar, collars_kg=collars)
    assert result.exact
    loaded = result.bar_grams + result.collar_grams + 2 * sum(p.grams * p.count for p in result.plates_per_side)
    assert loaded == result.target_grams


def test_fewest_plates_and_deterministic_output():
    first = calculate_load("120", inventory={Decimal("25"): 2, Decimal("10"): 5, Decimal("5"): 5})
    second = calculate_load(Decimal("120.000"), inventory={Decimal("5"): 5, Decimal("10"): 5, Decimal("25"): 2})
    assert first == second
    assert [(p.kg, p.count) for p in first.plates_per_side] == [("25", 2)]


def test_impossible_exact_load_is_reported():
    result = calculate_load("101", inventory={Decimal("25"): 4, Decimal("2.5"): 4})
    assert not result.exact
    assert "cannot be loaded exactly" in result.instruction


def test_decimal_precision_avoids_binary_float_errors():
    result = calculate_load(21.5, inventory={Decimal("0.25"): 4})
    assert result.exact
    assert result.plates_per_side[0].count == 3


@pytest.mark.parametrize("lift", ["squat", "bench", "deadlift"])
def test_warmups_are_monotonic_unique_and_include_opener_once(lift):
    plan = build_warmups(lift, 200 if lift != "bench" else 120)
    weights = [item.weight_grams for item in plan]
    assert weights == sorted(set(weights))
    assert sum(item.opener for item in plan) == 1
    assert all(b - a >= 2500 for a, b in zip(weights, weights[1:]))
    assert all(item.loading.exact for item in plan)


def test_inventory_is_bounded_and_manual_overrides_are_editable():
    inventory = default_inventory(0)
    inventory[Decimal("25")] = 4
    plan = build_warmups("squat", 120, overrides_kg=[20, 70], inventory=inventory)
    assert [item.weight_kg for item in plan] == ["20", "70", "120"]
