"""Coach-intent contract and conservative shorthand parser.

This module deliberately stops at an inspectable intent document.  It has no
dependency on programming models or persistence, so parsed free text cannot
write a programme.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Protocol, TypeVar, runtime_checkable


class BlockType(str, Enum):
    HYPERTROPHY = "hypertrophy"
    DEVELOPMENT = "development"
    STRENGTH = "strength"
    PEAKING = "peaking"
    OFFSEASON = "offseason"


class ChangeKind(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    CHANGE = "change"


class BodySide(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    BILATERAL = "bilateral"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True)
class Provenance:
    source: str
    text: str
    start: int
    end: int
    confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid source span")


T = TypeVar("T")


@dataclass(frozen=True)
class IntentValue(Generic[T]):
    value: T
    provenance: Provenance


@dataclass(frozen=True)
class RpeTarget:
    rpe: float
    week: int
    provenance: Provenance


@dataclass(frozen=True)
class PreserveDirective:
    subject: str
    provenance: Provenance


@dataclass(frozen=True)
class ChangeDirective:
    kind: ChangeKind
    subject: str
    target: str | None
    provenance: Provenance


@dataclass(frozen=True)
class AthleteObservation:
    observation: str
    location: str
    side: BodySide
    provenance: Provenance


@dataclass(frozen=True)
class CoachOverride:
    subject: str
    value: str
    provenance: Provenance


@dataclass(frozen=True)
class UnresolvedTerm:
    text: str
    reason: str
    provenance: Provenance


@dataclass(frozen=True)
class ProgrammingIntent:
    """Structured, reviewable input to a future programme proposal service."""

    source_text: str
    parser: str
    parser_version: str
    reference_programme: IntentValue[str] | None = None
    block_type: IntentValue[BlockType] | None = None
    duration_weeks: IntentValue[int] | None = None
    target_rpe: RpeTarget | None = None
    preserve: tuple[PreserveDirective, ...] = ()
    changes: tuple[ChangeDirective, ...] = ()
    athlete_observations: tuple[AthleteObservation, ...] = ()
    warm_up_intent: IntentValue[str] | None = None
    assistance_intent: IntentValue[str] | None = None
    coach_overrides: tuple[CoachOverride, ...] = ()
    unresolved: tuple[UnresolvedTerm, ...] = ()

    @property
    def review_required(self) -> bool:
        """Whether a coach must resolve uncertainty before proposal building."""
        return bool(self.unresolved)


@runtime_checkable
class ProgrammingIntentParser(Protocol):
    """Provider boundary for deterministic or future hosted parser adapters."""

    name: str
    version: str

    def parse(self, coach_text: str) -> ProgrammingIntent:
        """Return intent only; implementations must not write programmes."""
        ...


@dataclass
class _Draft:
    reference_programme: IntentValue[str] | None = None
    block_type: IntentValue[BlockType] | None = None
    duration_weeks: IntentValue[int] | None = None
    target_rpe: RpeTarget | None = None
    preserve: list[PreserveDirective] = field(default_factory=list)
    changes: list[ChangeDirective] = field(default_factory=list)
    observations: list[AthleteObservation] = field(default_factory=list)
    warm_up_intent: IntentValue[str] | None = None
    assistance_intent: IntentValue[str] | None = None
    overrides: list[CoachOverride] = field(default_factory=list)
    unresolved: list[UnresolvedTerm] = field(default_factory=list)
    consumed: list[tuple[int, int]] = field(default_factory=list)


class DeterministicProgrammingIntentParser:
    """Parse only explicit, documented coach shorthand; never infer intent."""

    name = "deterministic-shorthand"
    version = "1"

    _FLAGS = re.IGNORECASE
    _PATTERNS = {
        "reference": re.compile(
            r"\buse\s+(?:old\s+)?(?:sheet|block|programme|program)\s+"
            r"(?P<value>[^.;]+?)(?=\s+(?:for\s+)?\d+\s*[- ]?week\b|[.;]|$)",
            _FLAGS,
        ),
        "block": re.compile(
            r"\b(?P<weeks>\d+)\s*[- ]?week\s+(?P<type>hypertrophy|development|strength|peaking|off[- ]?season)\s+block\b",
            _FLAGS,
        ),
        "rpe": re.compile(
            r"\b(?:build|progress)\s+to\s+rpe\s*(?P<rpe>\d+(?:\.\d+)?)\s+"
            r"(?:in\s+)?week\s*(?P<week>\d+)\b",
            _FLAGS,
        ),
        "preserve": re.compile(
            r"\b(?:keep|preserve|maintain)\s+(?P<subject>[a-z][a-z0-9 /_-]*?)"
            r"(?=[.;]|\s+(?:and\s+)?(?:increase|decrease|change|add|include|override)\b|$)",
            _FLAGS,
        ),
        "change": re.compile(
            r"\b(?P<kind>increase|decrease|change)\s+"
            r"(?P<subject>[a-z][a-z0-9 /_-]*?)(?:\s+to\s+(?P<target>[^.;]+?))?"
            r"(?=[.;]|\s+(?:and\s+)?(?:keep|preserve|maintain|increase|decrease|change|add|include|override)\b|$)",
            _FLAGS,
        ),
        "observation": re.compile(
            r"\b(?:(?P<side>left|right|bilateral)(?:\s+side)?\s+)?"
            r"(?P<location>low(?:er)?\s+back|upper\s+back|shoulder|elbow|hip|knee|ankle|wrist)\s+"
            r"(?P<observation>pain|discomfort|tightness)\b",
            _FLAGS,
        ),
        "warmup": re.compile(
            r"\b(?:warm[- ]?up|warmup)\s*:\s*(?P<value>[^.;]+)", _FLAGS
        ),
        "assistance": re.compile(
            r"\b(?:assistance|accessories)\s*:\s*(?P<value>[^.;]+)", _FLAGS
        ),
        "override": re.compile(
            r"\boverride\s+(?P<subject>[a-z][a-z0-9 /_-]*?)\s*:\s*(?P<value>[^.;]+)",
            _FLAGS,
        ),
    }

    def parse(self, coach_text: str) -> ProgrammingIntent:
        if not isinstance(coach_text, str):
            raise TypeError("coach_text must be a string")
        text = coach_text.strip()
        draft = _Draft()
        if not text:
            draft.unresolved.append(self._unresolved(text, 0, 0, "intent is empty"))
            return self._finish(text, draft)

        self._single(text, draft, "reference", self._set_reference)
        self._single(text, draft, "block", self._set_block)
        self._single(text, draft, "rpe", self._set_rpe)
        self._many(text, draft, "preserve", self._add_preserve)
        self._many(text, draft, "change", self._add_change)
        self._many(text, draft, "observation", self._add_observation)
        self._single(text, draft, "warmup", self._set_warmup)
        self._single(text, draft, "assistance", self._set_assistance)
        self._many(text, draft, "override", self._add_override)

        if draft.duration_weeks and not 1 <= draft.duration_weeks.value <= 52:
            draft.unresolved.append(self._unresolved_from(
                draft.duration_weeks.provenance,
                "duration must be between 1 and 52 weeks",
            ))
        if draft.target_rpe:
            if not 1 <= draft.target_rpe.rpe <= 10:
                draft.unresolved.append(self._unresolved_from(
                    draft.target_rpe.provenance, "RPE must be between 1 and 10"
                ))
            if draft.duration_weeks and draft.target_rpe.week > draft.duration_weeks.value:
                draft.unresolved.append(self._unresolved_from(
                    draft.target_rpe.provenance,
                    "target week is outside the requested block duration",
                ))
            if draft.target_rpe.week < 1:
                draft.unresolved.append(self._unresolved_from(
                    draft.target_rpe.provenance, "target week must be at least 1"
                ))
        self._capture_unconsumed(text, draft)
        return self._finish(text, draft)

    def _single(self, text: str, draft: _Draft, key: str, setter) -> None:
        matches = list(self._PATTERNS[key].finditer(text))
        if not matches:
            return
        setter(text, draft, matches[0])
        for match in matches[1:]:
            draft.consumed.append(match.span())
            draft.unresolved.append(self._unresolved(
                text, *match.span(), f"multiple {key} directives require coach review"
            ))

    def _many(self, text: str, draft: _Draft, key: str, setter) -> None:
        for match in self._PATTERNS[key].finditer(text):
            setter(text, draft, match)

    def _provenance(self, text: str, match: re.Match[str], confidence: float = 1.0) -> Provenance:
        return Provenance("coach_text", match.group(0), *match.span(), confidence)

    def _mark(self, draft: _Draft, match: re.Match[str]) -> None:
        draft.consumed.append(match.span())

    def _set_reference(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.reference_programme = IntentValue(match["value"].strip(), self._provenance(text, match))
        self._mark(draft, match)

    def _set_block(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        provenance = self._provenance(text, match)
        kind = match["type"].casefold().replace("-", "").replace(" ", "")
        kind = "offseason" if kind == "offseason" else kind
        draft.duration_weeks = IntentValue(int(match["weeks"]), provenance)
        draft.block_type = IntentValue(BlockType(kind), provenance)
        self._mark(draft, match)

    def _set_rpe(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.target_rpe = RpeTarget(float(match["rpe"]), int(match["week"]), self._provenance(text, match))
        self._mark(draft, match)

    def _add_preserve(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.preserve.append(PreserveDirective(match["subject"].strip().casefold(), self._provenance(text, match)))
        self._mark(draft, match)

    def _add_change(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.changes.append(ChangeDirective(
            ChangeKind(match["kind"].casefold()), match["subject"].strip().casefold(),
            match["target"].strip() if match["target"] else None, self._provenance(text, match)
        ))
        self._mark(draft, match)

    def _add_observation(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        side = BodySide(match["side"].casefold()) if match["side"] else BodySide.UNSPECIFIED
        draft.observations.append(AthleteObservation(
            match["observation"].casefold(), match["location"].casefold(), side, self._provenance(text, match)
        ))
        self._mark(draft, match)

    def _set_warmup(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.warm_up_intent = IntentValue(match["value"].strip(), self._provenance(text, match))
        self._mark(draft, match)

    def _set_assistance(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.assistance_intent = IntentValue(match["value"].strip(), self._provenance(text, match))
        self._mark(draft, match)

    def _add_override(self, text: str, draft: _Draft, match: re.Match[str]) -> None:
        draft.overrides.append(CoachOverride(
            match["subject"].strip().casefold(), match["value"].strip(), self._provenance(text, match)
        ))
        self._mark(draft, match)

    def _capture_unconsumed(self, text: str, draft: _Draft) -> None:
        covered = [False] * len(text)
        for start, end in draft.consumed:
            covered[start:end] = [True] * (end - start)
        start = None
        for index in range(len(text) + 1):
            unknown = index < len(text) and not covered[index]
            if unknown and start is None:
                start = index
            elif not unknown and start is not None:
                raw = text[start:index]
                cleaned = re.sub(r"^[\s.;,]*(?:and\b\s*)?", "", raw, flags=self._FLAGS)
                cleaned = re.sub(r"[\s.;,]+$", "", cleaned)
                if cleaned:
                    offset = raw.find(cleaned)
                    left = start + offset
                    draft.unresolved.append(self._unresolved(
                        text, left, left + len(cleaned), "unsupported or ambiguous shorthand"
                    ))
                start = None

    def _unresolved(self, text: str, start: int, end: int, reason: str) -> UnresolvedTerm:
        value = text[start:end]
        return UnresolvedTerm(value, reason, Provenance("coach_text", value, start, end, 0.0))

    def _unresolved_from(self, source: Provenance, reason: str) -> UnresolvedTerm:
        return UnresolvedTerm(source.text, reason, Provenance(
            source.source, source.text, source.start, source.end, 0.0
        ))

    def _finish(self, text: str, draft: _Draft) -> ProgrammingIntent:
        return ProgrammingIntent(
            source_text=text, parser=self.name, parser_version=self.version,
            reference_programme=draft.reference_programme, block_type=draft.block_type,
            duration_weeks=draft.duration_weeks, target_rpe=draft.target_rpe,
            preserve=tuple(draft.preserve), changes=tuple(draft.changes),
            athlete_observations=tuple(draft.observations), warm_up_intent=draft.warm_up_intent,
            assistance_intent=draft.assistance_intent, coach_overrides=tuple(draft.overrides),
            unresolved=tuple(draft.unresolved),
        )
