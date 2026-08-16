from datetime import date, timedelta

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteConstraintFlag, CoachTechnicalObservation
from portal.services.programming_athlete_state import aggregate_programming_athlete_state


def _app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def _athlete():
    item = Athlete(first_name="Alex", last_name="Lifter", email="state@programming.test")
    db.session.add(item)
    db.session.flush()
    return item


def test_sided_hip_shift_is_a_recent_soft_signal_with_provenance():
    app = _app()
    with app.app_context():
        athlete = _athlete()
        db.session.add_all([
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Left hip shift out of the hole", observed_on=date(2026, 8, 10), recorded_by="coach@test"),
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Right hip shift on the final rep", observed_on=date(2026, 8, 11), recorded_by="coach@test"),
        ])
        db.session.commit()
        result = aggregate_programming_athlete_state(athlete, as_of=date(2026, 8, 12))
        assert [item["effects"]["side"] for item in result["soft_signals"]] == ["left", "right"]
        assert result["soft_signals"][0]["effects"]["warmup_protocol_keys"] == ["squat-hip-shift-preparation"]
        assert result["soft_signals"][0]["evidence"][0]["reference"] == "coach_technical_observation:1"
        assert result["hard_constraints"] == []


def test_elbow_irritation_and_low_back_pain_are_hard_non_diagnostic_filters():
    app = _app()
    with app.app_context():
        athlete = _athlete()
        db.session.add_all([
            AthleteConstraintFlag(athlete=athlete, flag_kind="irritation", label="Elbow irritation", reported_by="athlete", starts_on=date(2026, 8, 10)),
            AthleteConstraintFlag(athlete=athlete, flag_kind="irritation", label="Low-back pain", reported_by="athlete", starts_on=date(2026, 8, 11)),
        ])
        db.session.commit()
        result = aggregate_programming_athlete_state(athlete, as_of=date(2026, 8, 12))
        assert [item["effects"]["affected_regions"] for item in result["hard_constraints"]] == [["elbow"], ["low_back"]]
        assert result["consumer_hints"]["excluded_constraint_tags"] == ["axial_loading", "elbow_irritation", "elbow_loading", "low_back_loading"]
        assert "No diagnosis" in result["medical_scope"]
        assert all(item["evidence"] for item in result["hard_constraints"])


def test_shoulder_and_hip_irritation_produce_supported_programming_filters():
    app = _app()
    with app.app_context():
        athlete = _athlete()
        db.session.add_all([
            AthleteConstraintFlag(athlete=athlete, flag_kind="irritation", label="Shoulder irritation", reported_by="athlete", starts_on=date(2026, 8, 10)),
            AthleteConstraintFlag(athlete=athlete, flag_kind="irritation", label="Hip irritation", reported_by="athlete", starts_on=date(2026, 8, 10)),
        ])
        db.session.commit()

        result = aggregate_programming_athlete_state(athlete, as_of=date(2026, 8, 12))

        assert [item["effects"]["affected_regions"] for item in result["hard_constraints"]] == [["shoulder"], ["hip"]]
        assert result["consumer_hints"]["affected_lift_families"] == ["bench", "deadlift", "squat"]
        assert {"shoulder_loading", "overhead_loading", "hip_loading", "deep_hip_flexion"} <= set(result["consumer_hints"]["excluded_constraint_tags"])


def test_conflicting_technical_observations_require_review():
    app = _app()
    with app.app_context():
        athlete = _athlete()
        db.session.add_all([
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Left hip shift", observed_on=date(2026, 8, 10), recorded_by="coach@test"),
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Right hip shift", observed_on=date(2026, 8, 11), recorded_by="coach@test"),
        ])
        db.session.commit()

        result = aggregate_programming_athlete_state(athlete, as_of=date(2026, 8, 12))

        assert result["consumer_hints"]["review_required"] is True
        assert result["consumer_hints"]["review_reasons"] == [
            "Conflicting recent squat hip shift observations: left and right"
        ]


def test_resolved_and_stale_state_does_not_affect_current_programming():
    app = _app()
    as_of = date(2026, 8, 12)
    with app.app_context():
        athlete = _athlete()
        db.session.add_all([
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Left hip shift", observed_on=as_of - timedelta(days=28), recorded_by="coach@test"),
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Right hip shift", observed_on=as_of - timedelta(days=3), recorded_by="coach@test"),
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Right hip shift resolved", observed_on=as_of - timedelta(days=1), recorded_by="coach@test"),
            AthleteConstraintFlag(athlete=athlete, flag_kind="irritation", label="Elbow irritation", reported_by="athlete", starts_on=as_of - timedelta(days=14)),
            AthleteConstraintFlag(athlete=athlete, flag_kind="constraint", label="Deadlift constraint", reported_by="coach", starts_on=as_of - timedelta(days=3), resolved_on=as_of - timedelta(days=1)),
        ])
        db.session.commit()
        result = aggregate_programming_athlete_state(athlete, as_of=as_of)
        assert result["hard_constraints"] == []
        assert result["soft_signals"] == []
        assert result["missing_data"] is True


def test_missing_state_degrades_to_empty_explainable_contract():
    app = _app()
    with app.app_context():
        athlete = _athlete()
        db.session.commit()
        result = aggregate_programming_athlete_state(athlete, as_of=date(2026, 8, 12))
        assert result["missing_data"] is True
        assert result["consumer_hints"]["excluded_constraint_tags"] == []
