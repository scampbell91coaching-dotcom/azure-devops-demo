from decimal import Decimal

import pytest
from portal import create_app
from portal.attempt_selection import (
    AttemptSelectionError,
    AttemptStrategy,
    recommend_attempts,
)


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    return app.test_client()


def test_recommends_default_attempts_with_plate_rounding():
    result = recommend_attempts(lift="Squat", unit="kg", reference_load="203")

    assert result.attempts == (Decimal("182.5"), Decimal("192.5"), Decimal("202.5"))
    assert result.manual_override is False
    assert result.lift == "squat"


def test_supports_configurable_strategy_and_pound_units():
    strategy = AttemptStrategy(
        opener_percent=Decimal(88),
        second_percent=Decimal(94),
        third_percent=Decimal(101),
        rounding_increment=Decimal(5),
    )

    result = recommend_attempts(
        lift="deadlift", unit="lb", reference_load="500", strategy=strategy
    )

    assert result.attempts == (Decimal(440), Decimal(470), Decimal(505))
    assert result.strategy == strategy


def test_preserves_manual_override_without_rounding():
    result = recommend_attempts(
        lift="bench",
        unit="kg",
        reference_load="150",
        manual_attempts=("131", "141", "151"),
    )

    assert result.attempts == (Decimal(131), Decimal(141), Decimal(151))
    assert result.manual_override is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"lift": "curl"}, "Lift must be"),
        ({"unit": "stone"}, "Units must be"),
        ({"reference_load": "0"}, "Reference load must be greater"),
        (
            {
                "strategy": AttemptStrategy(
                    Decimal(95), Decimal(90), Decimal(100), Decimal("2.5")
                )
            },
            "percentages must increase",
        ),
        (
            {"manual_attempts": ("100", "100", "110")},
            "Manual attempts must increase",
        ),
    ],
)
def test_rejects_invalid_recommendation_inputs(changes, message):
    inputs = {"lift": "squat", "unit": "kg", "reference_load": "200"}
    inputs.update(changes)

    with pytest.raises(AttemptSelectionError, match=message):
        recommend_attempts(**inputs)


def test_rejects_rounding_that_collapses_attempt_progression():
    strategy = AttemptStrategy(Decimal(90), Decimal(91), Decimal(92), Decimal(10))

    with pytest.raises(AttemptSelectionError, match="Rounded attempts must increase"):
        recommend_attempts(
            lift="bench", unit="kg", reference_load="50", strategy=strategy
        )


def test_route_explains_inputs_strategy_and_defaults(client):
    response = client.get("/attempt-selection/")

    assert response.status_code == 200
    assert b"latest reliable single or conservative projected max" in response.data
    assert b"secure 90% opener" in response.data
    assert b"Coach override" in response.data


def test_route_renders_recommendation(client):
    response = client.post(
        "/attempt-selection/",
        data={
            "lift": "squat",
            "unit": "kg",
            "reference_load": "200",
            "opener_percent": "90",
            "second_percent": "95",
            "third_percent": "100",
            "rounding_increment": "2.5",
        },
    )

    assert response.status_code == 200
    assert b"Recommended plan" in response.data
    assert b"180 kg" in response.data
    assert b"190 kg" in response.data
    assert b"200 kg" in response.data


def test_route_preserves_manual_attempts_and_reports_partial_override(client):
    data = {
        "lift": "bench",
        "unit": "lb",
        "reference_load": "300",
        "opener_percent": "90",
        "second_percent": "95",
        "third_percent": "100",
        "rounding_increment": "5",
        "manual_1": "257",
        "manual_2": "281",
        "manual_3": "303",
    }
    response = client.post("/attempt-selection/", data=data)

    assert b"Coach override" in response.data
    assert b"257 lb" in response.data
    assert b"303 lb" in response.data
    assert b"never rounded or replaced" in response.data

    data["manual_2"] = ""
    response = client.post("/attempt-selection/", data=data)
    assert b"Enter all three manual attempts" in response.data
    assert b'value="257"' in response.data
