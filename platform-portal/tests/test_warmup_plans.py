import pytest

from portal.services.warmup_plans import (
    InMemoryWarmupProtocolRepository,
    InstructionKind,
    LiftFamily,
    OverrideAction,
    ProtocolScope,
    WarmupContext,
    WarmupInstruction,
    WarmupOverride,
    WarmupPhase,
    WarmupPlanService,
    WarmupProtocol,
    WarmupStep,
)


def reps(value: int = 8) -> WarmupInstruction:
    return WarmupInstruction(kind=InstructionKind.REPS, reps=value)


def step(key: str, phase: WarmupPhase, *, name: str | None = None) -> WarmupStep:
    instruction = (
        WarmupInstruction(kind=InstructionKind.BARBELL, reps=5, percentage=40)
        if phase is WarmupPhase.BARBELL_RAMP
        else reps()
    )
    return WarmupStep(key, phase, name or key.title(), instruction)


def protocol(
    key: str,
    *steps: WarmupStep,
    scope: ProtocolScope | None = None,
    priority: int = 100,
    active: bool = True,
) -> WarmupProtocol:
    return WarmupProtocol(
        protocol_id=key,
        name=key.title(),
        version="1",
        steps=steps,
        scope=scope or ProtocolScope(),
        priority=priority,
        active=active,
    )


def context(**changes: object) -> WarmupContext:
    values = {
        "athlete_id": 7,
        "session_id": 42,
        "lift_family": LiftFamily.SQUAT,
        "athlete_tags": frozenset({"coach-selected-ankle-prep"}),
        "session_tags": frozenset({"heavy"}),
    }
    values.update(changes)
    return WarmupContext(**values)  # type: ignore[arg-type]


def test_builds_complete_coaching_sequence_independent_of_input_order():
    repository = InMemoryWarmupProtocolRepository(
        [
            protocol("ramp", step("40-percent", WarmupPhase.BARBELL_RAMP)),
            protocol(
                "lift",
                step("squat-pattern", WarmupPhase.LIFT_PREPARATION),
                scope=ProtocolScope(lift_families=frozenset({LiftFamily.SQUAT})),
            ),
            protocol("general", step("pulse-raiser", WarmupPhase.GENERAL_PREPARATION)),
            protocol(
                "athlete",
                step("coach-intervention", WarmupPhase.ATHLETE_INTERVENTION),
                scope=ProtocolScope(athlete_ids=frozenset({7})),
            ),
        ]
    )

    plan = WarmupPlanService(repository).build(context())

    assert [item.phase for item in plan.steps] == list(WarmupPhase)
    assert plan.applied_protocols == ("athlete", "general", "lift", "ramp")
    assert all(item.provenance.source == "warmup_protocol" for item in plan.steps)
    assert plan.steps[0].provenance.version == "1"


def test_scope_combines_lift_athlete_and_session_context_without_inference():
    exact = protocol(
        "exact",
        step("selected", WarmupPhase.ATHLETE_INTERVENTION),
        scope=ProtocolScope(
            lift_families=frozenset({LiftFamily.SQUAT}),
            athlete_tags=frozenset({"coach-selected-ankle-prep"}),
            session_tags=frozenset({"heavy"}),
        ),
    )
    wrong_lift = protocol(
        "bench-only",
        step("bench", WarmupPhase.LIFT_PREPARATION),
        scope=ProtocolScope(lift_families=frozenset({LiftFamily.BENCH})),
    )
    inactive = protocol(
        "inactive", step("old", WarmupPhase.GENERAL_PREPARATION), active=False
    )

    plan = WarmupPlanService(
        InMemoryWarmupProtocolRepository([wrong_lift, inactive, exact])
    ).build(context())

    assert plan.applied_protocols == ("exact",)
    assert [item.key for item in plan.steps] == ["exact:selected"]


def test_priority_and_declared_step_order_are_stable_within_phase():
    service = WarmupPlanService(
        InMemoryWarmupProtocolRepository(
            [
                protocol("later", step("c", WarmupPhase.GENERAL_PREPARATION), priority=20),
                protocol(
                    "first",
                    step("a", WarmupPhase.GENERAL_PREPARATION),
                    step("b", WarmupPhase.GENERAL_PREPARATION),
                    priority=10,
                ),
            ]
        )
    )

    assert [item.key for item in service.build(context()).steps] == [
        "first:a",
        "first:b",
        "later:c",
    ]


def test_replace_remove_and_append_are_auditable_manual_overrides():
    service = WarmupPlanService(
        InMemoryWarmupProtocolRepository(
            [
                protocol(
                    "base",
                    step("general", WarmupPhase.GENERAL_PREPARATION),
                    step("lift", WarmupPhase.LIFT_PREPARATION),
                    step("ramp", WarmupPhase.BARBELL_RAMP),
                )
            ]
        )
    )
    replacement = step(
        "ignored-replacement-key", WarmupPhase.LIFT_PREPARATION, name="Coach choice"
    )
    addition = step("extra", WarmupPhase.ATHLETE_INTERVENTION)

    plan = service.build(
        context(),
        overrides=(
            WarmupOverride("remove-general", OverrideAction.REMOVE, "Not needed", "Coach", "base:general"),
            WarmupOverride("replace-lift", OverrideAction.REPLACE, "Session adjustment", "Coach", "base:lift", replacement),
            WarmupOverride("add-intervention", OverrideAction.APPEND, "Athlete-specific plan", "Coach", step=addition),
        ),
    )

    assert [item.key for item in plan.steps] == [
        "override:add-intervention",
        "base:lift",
        "base:ramp",
    ]
    replaced = plan.steps[1]
    assert replaced.name == "Coach choice"
    assert replaced.provenance.source == "manual_override"
    assert replaced.provenance.parent.source_id == "base"
    assert replaced.provenance.reason == "Coach: Session adjustment"
    assert plan.applied_overrides == (
        "remove-general",
        "replace-lift",
        "add-intervention",
    )


def test_unknown_override_target_fails_instead_of_silently_drifting():
    service = WarmupPlanService(InMemoryWarmupProtocolRepository())
    override = WarmupOverride(
        "missing", OverrideAction.REMOVE, "Coach edit", "Coach", "missing:step"
    )

    with pytest.raises(ValueError, match="override target does not exist"):
        service.build(context(), overrides=(override,))


@pytest.mark.parametrize(
    "instruction",
    [
        WarmupInstruction(kind=InstructionKind.REPS, reps=1),
        WarmupInstruction(kind=InstructionKind.DURATION, duration_seconds=30),
        WarmupInstruction(kind=InstructionKind.BARBELL, reps=3, percentage=70),
        WarmupInstruction(kind=InstructionKind.BARBELL, reps=1, load_kg=20),
    ],
)
def test_instruction_value_objects_accept_supported_prescriptions(instruction):
    assert instruction.sets == 1


def test_invalid_barbell_and_phase_combinations_are_rejected():
    with pytest.raises(ValueError, match="exactly one load target"):
        WarmupInstruction(
            kind=InstructionKind.BARBELL, reps=3, percentage=40, load_kg=20
        )
    with pytest.raises(ValueError, match="barbell ramp"):
        WarmupStep("ramp", WarmupPhase.BARBELL_RAMP, "Ramp", reps())


def test_duplicate_protocol_step_keys_are_rejected():
    duplicate = step("same", WarmupPhase.GENERAL_PREPARATION)
    with pytest.raises(ValueError, match="unique"):
        protocol("bad", duplicate, duplicate)
