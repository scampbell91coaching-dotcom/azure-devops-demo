from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

GRAMS_PER_KG = 1000
DEFAULT_PLATES_KG = (
    Decimal("25"), Decimal("20"), Decimal("15"), Decimal("10"),
    Decimal("5"), Decimal("2.5"), Decimal("1.25"), Decimal("0.5"),
    Decimal("0.25"),
)

# Competition-oriented default inventory, expressed per side of the bar.
# Heavy loading should continue using 25 kg plates while they are available
# rather than falling back to smaller denominations unnecessarily.
DEFAULT_PLATE_INVENTORY = {
    Decimal("25"): 20,
    Decimal("20"): 8,
    Decimal("15"): 8,
    Decimal("10"): 8,
    Decimal("5"): 4,
    Decimal("2.5"): 4,
    Decimal("1.25"): 4,
    Decimal("0.5"): 4,
    Decimal("0.25"): 4,
}
PLATE_COLOURS = {
    25000: "red", 20000: "blue", 15000: "yellow", 10000: "green",
    5000: "white", 2500: "black", 1250: "silver", 500: "silver",
    250: "silver",
}


def kg_to_grams(value: Decimal | str | int | float) -> int:
    try:
        kg = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Weight must be a number.") from exc
    grams = kg * GRAMS_PER_KG
    if not kg.is_finite() or grams != grams.to_integral_value():
        raise ValueError("Weights must be specified to the nearest gram.")
    return int(grams)


def format_kg(grams: int) -> str:
    return f"{Decimal(grams) / GRAMS_PER_KG:g}"


@dataclass(frozen=True)
class Plate:
    grams: int
    count: int
    colour: str

    @property
    def kg(self) -> str:
        return format_kg(self.grams)


@dataclass(frozen=True)
class LoadResult:
    target_grams: int
    bar_grams: int
    collar_grams: int
    plates_per_side: tuple[Plate, ...]
    exact: bool
    reason: str | None = None

    @property
    def target_kg(self) -> str:
        return format_kg(self.target_grams)

    @property
    def fixed_kg(self) -> str:
        return format_kg(self.bar_grams + self.collar_grams)

    @property
    def instruction(self) -> str:
        if not self.exact:
            return self.reason or "This target cannot be loaded exactly."
        if not self.plates_per_side:
            return "Load the bar and collars only."
        parts = [f"{plate.count} × {plate.kg} kg" for plate in self.plates_per_side]
        return "Per side, load " + ", then ".join(parts) + "."


def default_inventory(count_per_side: int | None = None) -> dict[Decimal, int]:
    if count_per_side is not None:
        return {weight: count_per_side for weight in DEFAULT_PLATES_KG}

    return DEFAULT_PLATE_INVENTORY.copy()




def calculate_load(
    target_kg: Decimal | str | int | float,
    *,
    bar_kg: Decimal | str | int | float = 20,
    collars_kg: Decimal | str | int | float = 0,
    inventory: Mapping[Decimal | str | int | float, int] | None = None,
) -> LoadResult:
    """Return the fewest exact plates per side using bounded integer-gram DP."""
    target = kg_to_grams(target_kg)
    bar = kg_to_grams(bar_kg)
    collars = kg_to_grams(collars_kg)
    remaining = target - bar - collars
    if remaining < 0:
        return LoadResult(target, bar, collars, (), False, "Target is lighter than the bar and collars.")
    if remaining % 2:
        return LoadResult(target, bar, collars, (), False, "The remaining load cannot be divided evenly between both sides.")
    per_side = remaining // 2
    source = inventory if inventory is not None else default_inventory()
    available = sorted(
        ((kg_to_grams(weight), int(count)) for weight, count in source.items() if int(count) > 0),
        reverse=True,
    )
    # total -> tuple of counts in descending plate order; keep the fewest plates.
    states: dict[int, tuple[int, ...]] = {0: (0,) * len(available)}
    for index, (weight, count) in enumerate(available):
        next_states = dict(states)
        for subtotal, counts in states.items():
            for used in range(1, count + 1):
                total = subtotal + weight * used
                if total > per_side:
                    break
                candidate = counts[:index] + (used,) + counts[index + 1 :]
                existing = next_states.get(total)
                if existing is None or (sum(candidate), tuple(-n for n in candidate)) < (sum(existing), tuple(-n for n in existing)):
                    next_states[total] = candidate
        states = next_states
    counts = states.get(per_side)
    if counts is None:
        return LoadResult(target, bar, collars, (), False, "Target cannot be loaded exactly with the available plate inventory.")
    plates = tuple(
        Plate(weight, count, PLATE_COLOURS.get(weight, "black"))
        for (weight, _), count in zip(available, counts)
        if count
    )
    return LoadResult(target, bar, collars, plates, True)


@dataclass(frozen=True)
class WarmupSet:
    sequence: int
    weight_grams: int
    repetitions: int
    percentage: int
    loading: LoadResult
    opener: bool = False

    @property
    def weight_kg(self) -> str:
        return format_kg(self.weight_grams)


DEFAULT_PERCENTAGES = {
    "squat": (0, 40, 55, 70, 82, 92),
    "bench": (0, 35, 50, 62, 74, 84, 92),
    "deadlift": (40, 55, 70, 82, 92),
}


def build_warmups(
    lift: str,
    opener_kg: Decimal | str | int | float,
    *,
    bar_kg: Decimal | str | int | float = 20,
    collars_kg: Decimal | str | int | float = 0,
    first_loaded_kg: Decimal | str | int | float | None = None,
    stages: int | None = None,
    minimum_increment_kg: Decimal | str | int | float = Decimal("2.5"),
    inventory: Mapping[Decimal | str | int | float, int] | None = None,
    overrides_kg: Sequence[Decimal | str | int | float] | None = None,
) -> tuple[WarmupSet, ...]:
    if lift not in DEFAULT_PERCENTAGES:
        raise ValueError("Lift must be squat, bench, or deadlift.")
    opener = kg_to_grams(opener_kg)
    bar = kg_to_grams(bar_kg)
    collars = kg_to_grams(collars_kg)
    fixed = bar + collars
    increment = kg_to_grams(minimum_increment_kg)
    if opener <= fixed or increment <= 0:
        raise ValueError("Opener must exceed the bar and collars, and increment must be positive.")
    if overrides_kg:
        candidates = [kg_to_grams(value) for value in overrides_kg]
    else:
        percentages = DEFAULT_PERCENTAGES[lift]
        if stages is not None:
            if stages < 1 or stages > len(percentages):
                raise ValueError("Warm-up stages must be within the supported range.")
            percentages = percentages[-stages:]
        candidates = []
        for percent in percentages:
            raw = fixed if percent == 0 else opener * percent // 100
            rounded = max(fixed, (raw // increment) * increment)
            candidates.append(rounded)
        if first_loaded_kg is not None:
            first = kg_to_grams(first_loaded_kg)
            candidates = [fixed] + [weight for weight in candidates if weight >= first]
            if fixed < first < opener:
                candidates.insert(1, first)
    candidates.append(opener)
    weights: list[int] = []
    for weight in candidates:
        if weight < fixed or weight > opener or (weights and weight - weights[-1] < increment):
            continue
        load = calculate_load(Decimal(weight) / GRAMS_PER_KG, bar_kg=bar_kg, collars_kg=collars_kg, inventory=inventory)
        if load.exact:
            weights.append(weight)
    if not weights or weights[-1] != opener:
        opener_load = calculate_load(opener_kg, bar_kg=bar_kg, collars_kg=collars_kg, inventory=inventory)
        if not opener_load.exact:
            raise ValueError(opener_load.reason or "Opener cannot be loaded exactly.")
        weights.append(opener)
    result = []
    for index, weight in enumerate(weights, 1):
        percentage = round(weight * 100 / opener)
        reps = 5 if percentage <= 40 else 3 if percentage <= 60 else 2 if percentage <= 82 else 1
        result.append(WarmupSet(index, weight, reps, percentage, calculate_load(Decimal(weight) / GRAMS_PER_KG, bar_kg=bar_kg, collars_kg=collars_kg, inventory=inventory), weight == opener))
    return tuple(result)
