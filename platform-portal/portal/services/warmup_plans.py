"""Migration-free warm-up planning domain.

The types in this module deliberately have no Flask or SQLAlchemy dependency.  A
future database adapter only needs to implement :class:`WarmupProtocolRepository`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum, IntEnum
from typing import Protocol


class WarmupPhase(IntEnum):
    GENERAL_PREPARATION = 10
    ATHLETE_INTERVENTION = 20
    LIFT_PREPARATION = 30
    BARBELL_RAMP = 40


class LiftFamily(str, Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"


class InstructionKind(str, Enum):
    REPS = "reps"
    DURATION = "duration"
    BARBELL = "barbell"


class OverrideAction(str, Enum):
    REMOVE = "remove"
    REPLACE = "replace"
    APPEND = "append"


@dataclass(frozen=True)
class Provenance:
    source: str
    source_id: str
    version: str | None = None
    reason: str | None = None
    parent: Provenance | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.source_id.strip():
            raise ValueError("provenance source and source_id are required")


@dataclass(frozen=True)
class WarmupInstruction:
    kind: InstructionKind
    sets: int = 1
    reps: int | None = None
    duration_seconds: int | None = None
    percentage: float | None = None
    load_kg: float | None = None
    rest_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.sets < 1:
            raise ValueError("sets must be positive")
        if self.rest_seconds is not None and self.rest_seconds < 0:
            raise ValueError("rest_seconds cannot be negative")
        if self.kind is InstructionKind.REPS:
            if self.reps is None or self.reps < 1:
                raise ValueError("rep instructions require positive reps")
        elif self.kind is InstructionKind.DURATION:
            if self.duration_seconds is None or self.duration_seconds < 1:
                raise ValueError("duration instructions require a positive duration")
        elif self.kind is InstructionKind.BARBELL:
            targets = (self.percentage is not None, self.load_kg is not None)
            if sum(targets) != 1:
                raise ValueError("barbell instructions require exactly one load target")
            if self.percentage is not None and not 0 < self.percentage <= 100:
                raise ValueError("percentage must be in (0, 100]")
            if self.load_kg is not None and self.load_kg < 0:
                raise ValueError("load_kg cannot be negative")
            if self.reps is None or self.reps < 1:
                raise ValueError("barbell instructions require positive reps")


@dataclass(frozen=True)
class WarmupStep:
    key: str
    phase: WarmupPhase
    name: str
    instruction: WarmupInstruction
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.name.strip():
            raise ValueError("step key and name are required")
        if (
            self.phase is WarmupPhase.BARBELL_RAMP
            and self.instruction.kind is not InstructionKind.BARBELL
        ):
            raise ValueError("barbell ramp steps require a barbell instruction")


@dataclass(frozen=True)
class ProtocolScope:
    lift_families: frozenset[LiftFamily] = field(default_factory=frozenset)
    athlete_ids: frozenset[int] = field(default_factory=frozenset)
    athlete_tags: frozenset[str] = field(default_factory=frozenset)
    session_tags: frozenset[str] = field(default_factory=frozenset)

    def matches(self, context: WarmupContext) -> bool:
        return (
            (not self.lift_families or context.lift_family in self.lift_families)
            and (not self.athlete_ids or context.athlete_id in self.athlete_ids)
            and self.athlete_tags <= context.athlete_tags
            and self.session_tags <= context.session_tags
        )


@dataclass(frozen=True)
class WarmupProtocol:
    protocol_id: str
    name: str
    version: str
    steps: tuple[WarmupStep, ...]
    scope: ProtocolScope = field(default_factory=ProtocolScope)
    priority: int = 100
    active: bool = True

    def __post_init__(self) -> None:
        if not self.protocol_id.strip() or not self.name.strip() or not self.version.strip():
            raise ValueError("protocol id, name, and version are required")
        keys = [step.key for step in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("step keys must be unique within a protocol")


@dataclass(frozen=True)
class WarmupContext:
    athlete_id: int
    session_id: int | str
    lift_family: LiftFamily
    athlete_tags: frozenset[str] = field(default_factory=frozenset)
    session_tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.athlete_id < 1:
            raise ValueError("athlete_id must be positive")
        if not str(self.session_id).strip():
            raise ValueError("session_id is required")


@dataclass(frozen=True)
class WarmupOverride:
    override_id: str
    action: OverrideAction
    reason: str
    actor: str
    target_key: str | None = None
    step: WarmupStep | None = None

    def __post_init__(self) -> None:
        if not self.override_id.strip() or not self.reason.strip() or not self.actor.strip():
            raise ValueError("override id, reason, and actor are required")
        if self.action in {OverrideAction.REMOVE, OverrideAction.REPLACE} and not self.target_key:
            raise ValueError(f"{self.action.value} requires target_key")
        if self.action in {OverrideAction.REPLACE, OverrideAction.APPEND} and self.step is None:
            raise ValueError(f"{self.action.value} requires a step")
        if self.action is OverrideAction.REMOVE and self.step is not None:
            raise ValueError("remove cannot carry a replacement step")


@dataclass(frozen=True)
class PlannedWarmupStep:
    key: str
    phase: WarmupPhase
    name: str
    instruction: WarmupInstruction
    notes: str | None
    provenance: Provenance


@dataclass(frozen=True)
class WarmupPlan:
    athlete_id: int
    session_id: int | str
    lift_family: LiftFamily
    steps: tuple[PlannedWarmupStep, ...]
    applied_protocols: tuple[str, ...]
    applied_overrides: tuple[str, ...]
    applied_assignments: tuple[str, ...] = ()


@dataclass(frozen=True)
class WarmupProtocolAssignment:
    """An explicit, auditable link between a protocol version and a plan context."""

    assignment_id: str
    protocol_id: str
    protocol_version: str
    assigned_by: str
    reason: str

    def __post_init__(self) -> None:
        required = (
            self.assignment_id,
            self.protocol_id,
            self.protocol_version,
            self.assigned_by,
            self.reason,
        )
        if any(not value.strip() for value in required):
            raise ValueError(
                "assignment identity, protocol version, actor, and reason are required"
            )


class WarmupProtocolRepository(Protocol):
    """Persistence seam; adapters return domain objects, never ORM rows."""

    def list_active(self) -> Sequence[WarmupProtocol]: ...


class AssignedWarmupPlanRepository(Protocol):
    """Schema-independent read seam for one athlete/session/lift plan."""

    def list_assignments(
        self, context: WarmupContext
    ) -> Sequence[WarmupProtocolAssignment]: ...

    def list_overrides(self, context: WarmupContext) -> Sequence[WarmupOverride]: ...


class WarmupPlanSnapshotRepository(Protocol):
    """Write seam implemented later by the transaction-owning database adapter."""

    def save_resolved(self, plan: WarmupPlan) -> None: ...


class InMemoryWarmupProtocolRepository:
    """Useful for configuration-backed protocols and tests before persistence."""

    def __init__(self, protocols: Iterable[WarmupProtocol] = ()) -> None:
        self._protocols = tuple(protocols)

    def list_active(self) -> Sequence[WarmupProtocol]:
        return tuple(protocol for protocol in self._protocols if protocol.active)


class WarmupPlanService:
    def __init__(self, repository: WarmupProtocolRepository) -> None:
        self._repository = repository

    def build(
        self,
        context: WarmupContext,
        *,
        overrides: Sequence[WarmupOverride] = (),
    ) -> WarmupPlan:
        protocols = sorted(
            (
                protocol
                for protocol in self._repository.list_active()
                if protocol.active and protocol.scope.matches(context)
            ),
            key=lambda item: (item.priority, item.protocol_id, item.version),
        )
        planned: list[tuple[int, int, PlannedWarmupStep]] = []
        for protocol_order, protocol in enumerate(protocols):
            for step_order, step in enumerate(protocol.steps):
                planned.append(
                    (
                        protocol_order,
                        step_order,
                        PlannedWarmupStep(
                            key=f"{protocol.protocol_id}:{step.key}",
                            phase=step.phase,
                            name=step.name,
                            instruction=step.instruction,
                            notes=step.notes,
                            provenance=Provenance(
                                source="warmup_protocol",
                                source_id=protocol.protocol_id,
                                version=protocol.version,
                            ),
                        ),
                    )
                )
        planned.sort(key=lambda item: (item[2].phase, item[0], item[1]))
        steps = [item[2] for item in planned]

        applied: list[str] = []
        for override in overrides:
            index = next(
                (i for i, item in enumerate(steps) if item.key == override.target_key),
                None,
            )
            if override.action in {OverrideAction.REMOVE, OverrideAction.REPLACE} and index is None:
                raise ValueError(f"override target does not exist: {override.target_key}")
            if override.action is OverrideAction.REMOVE:
                steps.pop(index)  # type: ignore[arg-type]
            else:
                assert override.step is not None
                parent = steps[index].provenance if index is not None else None
                replacement = PlannedWarmupStep(
                    key=(override.target_key if index is not None else f"override:{override.override_id}"),
                    phase=override.step.phase,
                    name=override.step.name,
                    instruction=override.step.instruction,
                    notes=override.step.notes,
                    provenance=Provenance(
                        source="manual_override",
                        source_id=override.override_id,
                        reason=f"{override.actor}: {override.reason}",
                        parent=parent,
                    ),
                )
                if index is None:
                    steps.append(replacement)
                else:
                    steps[index] = replacement
            applied.append(override.override_id)

        # Phase order is a domain invariant; stable sorting preserves protocol and
        # explicit override ordering within each phase.
        steps.sort(key=lambda item: item.phase)
        return WarmupPlan(
            athlete_id=context.athlete_id,
            session_id=context.session_id,
            lift_family=context.lift_family,
            steps=tuple(steps),
            applied_protocols=tuple(item.protocol_id for item in protocols),
            applied_overrides=tuple(applied),
        )


class AssignedWarmupPlanService:
    """Resolve only explicitly assigned protocol versions, then optionally snapshot."""

    def __init__(
        self,
        protocols: WarmupProtocolRepository,
        plans: AssignedWarmupPlanRepository,
        snapshots: WarmupPlanSnapshotRepository | None = None,
    ) -> None:
        self._protocols = protocols
        self._plans = plans
        self._snapshots = snapshots

    def build(self, context: WarmupContext, *, save_snapshot: bool = False) -> WarmupPlan:
        assignments = tuple(self._plans.list_assignments(context))
        assigned_versions = {
            (item.protocol_id, item.protocol_version) for item in assignments
        }
        assigned_protocols = {item.protocol_id for item in assignments}
        if len(assigned_versions) != len(assigned_protocols):
            raise ValueError("multiple versions of one protocol are assigned")
        available = {
            (item.protocol_id, item.version): item
            for item in self._protocols.list_active()
        }
        missing = sorted(assigned_versions - available.keys())
        if missing:
            joined = ", ".join(f"{protocol}@{version}" for protocol, version in missing)
            raise ValueError(f"assigned protocol version is unavailable: {joined}")

        selected = [available[key] for key in assigned_versions]
        plan = WarmupPlanService(InMemoryWarmupProtocolRepository(selected)).build(
            context,
            overrides=self._plans.list_overrides(context),
        )
        applied_protocols = set(plan.applied_protocols)
        plan = replace(
            plan,
            applied_assignments=tuple(
                item.assignment_id
                for item in assignments
                if item.protocol_id in applied_protocols
            ),
        )
        if save_snapshot:
            if self._snapshots is None:
                raise ValueError(
                    "snapshot repository is required to save a resolved plan"
                )
            self._snapshots.save_resolved(plan)
        return plan
