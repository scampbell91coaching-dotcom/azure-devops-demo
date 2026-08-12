import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.programming_services.references import (
    ReferenceIsolationError,
    ReferenceResolutionError,
    proposal_diff,
    reference_snapshot,
    resolve_reference_block,
)


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def _athlete(email: str) -> Athlete:
    athlete = Athlete(first_name="Jack", last_name="Lifter", email=email)
    db.session.add(athlete)
    db.session.flush()
    return athlete


def _block(athlete: Athlete, name: str, *, status: str = "archived", rpe: float = 7.0) -> TrainingBlock:
    block = TrainingBlock(athlete=athlete, name=name, status=status, objective="Strength")
    db.session.add(block)
    db.session.flush()
    for week_number, week_rpe in ((1, rpe), (2, rpe + 1)):
        week = TrainingWeek(block=block, name=f"Week {week_number}", position=week_number)
        session = TrainingSession(week=week, name="Squat day", day_label="Monday", position=1)
        db.session.add_all((week, session))
        db.session.flush()
        slot = ProgrammingLiftSlot(session=session, position=1, lift_family="squat")
        db.session.add(slot)
        db.session.flush()
        db.session.add(ExercisePrescription(
            session=session, lift_slot=slot, exercise_name="High Bar Squat", position=1,
            prescription_type="rpe", sets=3, reps="5", rpe=week_rpe,
            slot_role="top_set", provenance="coach_authored",
        ))
    db.session.flush()
    return block


def test_resolves_named_historical_block_only_within_current_athlete(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        other = _athlete("other@example.test")
        expected = _block(jack, "Old Sheet Jack 1")
        _block(other, "Old Sheet Jack 1")
        db.session.commit()

        resolved = resolve_reference_block(jack.id, name=" old sheet jack 1 ")
        assert resolved.id == expected.id
        assert resolved.status == "archived"


def test_selected_id_cannot_cross_athlete_boundary_or_reveal_match(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        other = _athlete("other@example.test")
        private = _block(other, "Private competition peak")
        db.session.commit()

        with pytest.raises(ReferenceResolutionError, match="for this athlete") as error:
            resolve_reference_block(jack.id, block_id=private.id)
        assert "Private competition peak" not in str(error.value)


def test_named_reference_must_be_unique_and_selection_must_be_explicit(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        _block(jack, "Old Sheet Jack 1")
        _block(jack, "OLD SHEET JACK 1")
        db.session.commit()

        with pytest.raises(ReferenceResolutionError, match="uniquely resolve"):
            resolve_reference_block(jack.id, name="old sheet jack 1")
        with pytest.raises(ReferenceResolutionError, match="Select one"):
            resolve_reference_block(jack.id)
        with pytest.raises(ReferenceResolutionError, match="Select one"):
            resolve_reference_block(jack.id, block_id=1, name="old sheet jack 1")


def test_reference_snapshot_captures_architecture_and_progression_without_ids(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        block = _block(jack, "Old Sheet Jack 1")
        db.session.commit()

        snapshot = reference_snapshot(block)
        assert snapshot["lift_exposure_frequency"] == [
            {"week": 1, "squat": 1, "bench": 0, "deadlift": 0},
            {"week": 2, "squat": 1, "bench": 0, "deadlift": 0},
        ]
        assert snapshot["lift_variations"][0]["squat"] == ["High Bar Squat"]
        assert snapshot["progression_shape"][0]["target_directions"]["rpe"] == [
            "baseline", "increase"
        ]
        assert snapshot["policy"]["preserved"] == [
            "split", "lift_exposure_frequency", "lift_variations", "progression_shape"
        ]
        assert '"id"' not in str(snapshot)


def test_proposal_diff_separates_preserved_architecture_from_changeable_targets(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        reference = _block(jack, "Old Sheet Jack 1", rpe=7.0)
        proposal = _block(jack, "Jack 2 proposal", status="draft", rpe=7.5)
        # A structural exposure change must be visible as a preservation violation.
        proposal.weeks[0].sessions[0].lift_slots[0].lift_family = "bench"
        db.session.commit()

        result = proposal_diff(reference, proposal)
        assert result.reference_block_id == reference.id
        assert result.proposal_block_id == proposal.id
        assert any(change.path.startswith("lift_exposure_frequency") for change in result.preserved_changes)
        assert any(change.path.startswith("progression_shape") for change in result.preserved_changes)
        assert any(change.path.startswith("prescriptions") and change.proposal == 7.5
                   for change in result.eligible_changes)
        assert proposal.status == "draft"


def test_shifted_targets_preserve_the_same_progression_shape(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        reference = _block(jack, "Old Sheet Jack 1", rpe=7.0)
        proposal = _block(jack, "Jack 2 proposal", status="draft", rpe=7.5)
        db.session.commit()

        result = proposal_diff(reference, proposal)
        assert not any(
            change.path.startswith("progression_shape")
            for change in result.preserved_changes
        )
        assert any(
            change.path.startswith("prescriptions")
            for change in result.eligible_changes
        )


def test_proposal_diff_rejects_cross_athlete_comparison(app):
    with app.app_context():
        jack = _athlete("jack@example.test")
        other = _athlete("other@example.test")
        reference = _block(jack, "Jack 1")
        proposal = _block(other, "Other proposal", status="draft")
        db.session.commit()

        with pytest.raises(ReferenceIsolationError, match="same athlete"):
            proposal_diff(reference, proposal)
