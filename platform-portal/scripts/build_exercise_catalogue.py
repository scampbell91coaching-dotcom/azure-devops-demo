"""Build the reviewed Traditional Strength starter exercise catalogue.

Run from the repository root. The compact source lists make duplicate review
practical; the emitted JSON is the production import asset.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "traditional_strength_intelligence.json"


SQUAT = [
    ("Competition Squat", "competition", "barbell"),
    ("High-Bar Back Squat", "variation", "barbell"),
    ("Low-Bar Back Squat", "variation", "barbell"),
    ("Front Squat", "variation", "barbell"),
    ("Safety-Bar Squat", "variation", "safety squat bar"),
    ("Pause Squat", "variation", "barbell"),
    ("Tempo Squat", "variation", "barbell"),
    ("Pin Squat", "variation", "barbell and rack"),
    ("Box Squat", "variation", "barbell and box"),
    ("Anderson Squat", "variation", "barbell and rack"),
    ("Hatfield Squat", "variation", "safety squat bar and rack"),
    ("Zercher Squat", "variation", "barbell"),
    ("Overhead Squat", "variation", "barbell"),
    ("Goblet Squat", "regression", "dumbbell or kettlebell"),
    ("Landmine Squat", "regression", "landmine"),
    ("Belt Squat", "variation", "belt squat machine"),
    ("Hack Squat", "variation", "hack squat machine"),
    ("Smith Machine Squat", "variation", "Smith machine"),
    ("Cyclist Squat", "variation", "dumbbell and heel wedge"),
    ("Heels-Elevated Squat", "variation", "barbell and heel wedge"),
    ("Wide-Stance Squat", "variation", "barbell"),
    ("Narrow-Stance Squat", "variation", "barbell"),
    ("Cambered-Bar Squat", "variation", "cambered bar"),
    ("Duffalo-Bar Squat", "variation", "cambered bar"),
    ("Paused Front Squat", "variation", "barbell"),
    ("Tempo Front Squat", "variation", "barbell"),
    ("Double-Pause Squat", "variation", "barbell"),
    ("Three-Quarter Squat", "variation", "barbell"),
    ("Wall Squat", "regression", "bodyweight"),
    ("Counterbalance Squat", "regression", "weight plate"),
]

BENCH = [
    ("Competition Bench Press", "competition", "barbell and bench"),
    ("Touch-and-Go Bench Press", "variation", "barbell and bench"),
    ("Paused Bench Press", "variation", "barbell and bench"),
    ("Long-Pause Bench Press", "variation", "barbell and bench"),
    ("Tempo Bench Press", "variation", "barbell and bench"),
    ("Close-Grip Bench Press", "variation", "barbell and bench"),
    ("Wide-Grip Bench Press", "variation", "barbell and bench"),
    ("Spoto Press", "variation", "barbell and bench"),
    ("Larsen Press", "variation", "barbell and bench"),
    ("Feet-Up Bench Press", "variation", "barbell and bench"),
    ("Floor Press", "variation", "barbell"),
    ("Pin Bench Press", "variation", "barbell, bench and rack"),
    ("Board Press", "variation", "barbell, bench and board"),
    ("Slingshot Bench Press", "variation", "barbell, bench and bench aid"),
    ("Incline Barbell Bench Press", "variation", "barbell and incline bench"),
    ("Decline Barbell Bench Press", "variation", "barbell and decline bench"),
    ("Reverse-Grip Bench Press", "variation", "barbell and bench"),
    ("Swiss-Bar Bench Press", "variation", "multi-grip bar and bench"),
    ("Football-Bar Bench Press", "variation", "multi-grip bar and bench"),
    ("Dumbbell Bench Press", "variation", "dumbbells and bench"),
    ("Neutral-Grip Dumbbell Bench Press", "variation", "dumbbells and bench"),
    ("Single-Arm Dumbbell Bench Press", "variation", "dumbbell and bench"),
    ("Incline Dumbbell Bench Press", "variation", "dumbbells and incline bench"),
    ("Machine Chest Press", "regression", "chest press machine"),
    ("Smith Machine Bench Press", "variation", "Smith machine and bench"),
    ("Push-Up", "regression", "bodyweight"),
    ("Band-Resisted Bench Press", "variation", "barbell, bench and bands"),
    ("Chain Bench Press", "variation", "barbell, bench and chains"),
    ("Dead Bench Press", "variation", "barbell, bench and rack"),
    ("One-Board Bench Press", "variation", "barbell, bench and board"),
]

HINGE = [
    ("Competition Deadlift", "competition", "barbell"),
    ("Conventional Deadlift", "variation", "barbell"),
    ("Sumo Deadlift", "variation", "barbell"),
    ("Romanian Deadlift", "variation", "barbell"),
    ("Stiff-Leg Deadlift", "variation", "barbell"),
    ("Paused Deadlift", "variation", "barbell"),
    ("Tempo Deadlift", "variation", "barbell"),
    ("Deficit Deadlift", "variation", "barbell and platform"),
    ("Block Pull", "variation", "barbell and blocks"),
    ("Rack Pull", "variation", "barbell and rack"),
    ("Snatch-Grip Deadlift", "variation", "barbell"),
    ("Trap-Bar Deadlift", "variation", "trap bar"),
    ("Dumbbell Romanian Deadlift", "variation", "dumbbells"),
    ("Single-Leg Romanian Deadlift", "unilateral", "dumbbells"),
    ("Kickstand Romanian Deadlift", "unilateral", "dumbbells"),
    ("Good Morning", "variation", "barbell"),
    ("Safety-Bar Good Morning", "variation", "safety squat bar"),
    ("Seated Good Morning", "variation", "barbell and bench"),
    ("Cable Pull-Through", "regression", "cable"),
    ("Kettlebell Swing", "variation", "kettlebell"),
    ("Barbell Hip Thrust", "variation", "barbell and bench"),
    ("Machine Hip Thrust", "regression", "hip thrust machine"),
    ("Glute Bridge", "regression", "bodyweight"),
    ("45-Degree Back Extension", "regression", "back extension bench"),
    ("Reverse Hyperextension", "variation", "reverse hyper machine"),
    ("Cable Romanian Deadlift", "regression", "cable"),
    ("Band Good Morning", "regression", "resistance band"),
    ("Suitcase Deadlift", "variation", "dumbbell or kettlebell"),
    ("Jefferson Deadlift", "advanced", "barbell"),
    ("Clean-Grip Deadlift", "variation", "barbell"),
]


ACCESSORIES = {
    "Back": [
        "Pull-Up",
        "Chin-Up",
        "Neutral-Grip Pull-Up",
        "Band-Assisted Pull-Up",
        "Lat Pulldown",
        "Neutral-Grip Lat Pulldown",
        "Single-Arm Lat Pulldown",
        "Straight-Arm Pulldown",
        "Barbell Row",
        "Pendlay Row",
        "Dumbbell Row",
        "Chest-Supported Dumbbell Row",
        "Seal Row",
        "Cable Row",
        "Machine Row",
        "Meadows Row",
        "Inverted Row",
        "T-Bar Row",
        "Helms Row",
        "Shrug",
    ],
    "Quads": [
        "Leg Extension",
        "Single-Leg Extension",
        "Leg Press",
        "Single-Leg Press",
        "Walking Lunge",
        "Reverse Lunge",
        "Forward Lunge",
        "Lateral Lunge",
        "Bulgarian Split Squat",
        "Front-Foot-Elevated Split Squat",
        "Step-Up",
        "Step-Down",
        "Reverse Nordic Curl",
        "Spanish Squat",
        "Sissy Squat",
        "Wall Sit",
        "Sled Push",
        "Backward Sled Drag",
        "Dumbbell Split Squat",
        "Smith Machine Split Squat",
    ],
    "Hamstrings": [
        "Seated Leg Curl",
        "Lying Leg Curl",
        "Standing Leg Curl",
        "Single-Leg Curl",
        "Nordic Hamstring Curl",
        "Assisted Nordic Hamstring Curl",
        "Slider Leg Curl",
        "Stability-Ball Leg Curl",
        "Glute-Ham Raise",
        "Razor Curl",
        "Banded Leg Curl",
        "Cable Leg Curl",
    ],
    "Glutes": [
        "Cable Hip Abduction",
        "Machine Hip Abduction",
        "Banded Hip Abduction",
        "Cable Kickback",
        "Quadruped Hip Extension",
        "Frog Pump",
        "Single-Leg Glute Bridge",
        "B-Stance Hip Thrust",
        "Single-Leg Hip Thrust",
        "Dumbbell Hip Thrust",
        "Lateral Band Walk",
        "Monster Walk",
    ],
    "Shoulders": [
        "Standing Overhead Press",
        "Seated Barbell Press",
        "Dumbbell Shoulder Press",
        "Arnold Press",
        "Landmine Press",
        "Single-Arm Landmine Press",
        "Machine Shoulder Press",
        "Lateral Raise",
        "Cable Lateral Raise",
        "Machine Lateral Raise",
        "Lean-Away Lateral Raise",
        "Rear-Delt Fly",
        "Reverse Pec Deck",
        "Face Pull",
        "Band Pull-Apart",
        "Prone Y Raise",
        "Prone T Raise",
        "Cuban Rotation",
        "Cable External Rotation",
        "Dumbbell External Rotation",
    ],
    "Chest": [
        "Dumbbell Fly",
        "Incline Dumbbell Fly",
        "Cable Fly",
        "Low-to-High Cable Fly",
        "High-to-Low Cable Fly",
        "Pec Deck",
        "Cable Press-Around",
        "Deficit Push-Up",
        "Incline Push-Up",
        "Kneeling Push-Up",
        "Dip",
        "Assisted Dip",
    ],
    "Triceps": [
        "Cable Triceps Pressdown",
        "Rope Triceps Pressdown",
        "Overhead Cable Triceps Extension",
        "Dumbbell Triceps Extension",
        "Skull Crusher",
        "JM Press",
        "Rolling Dumbbell Extension",
        "Cross-Body Cable Extension",
        "Single-Arm Pressdown",
        "Bench Dip",
    ],
    "Biceps": [
        "Barbell Curl",
        "EZ-Bar Curl",
        "Dumbbell Curl",
        "Hammer Curl",
        "Incline Dumbbell Curl",
        "Preacher Curl",
        "Cable Curl",
        "Bayesian Cable Curl",
        "Reverse Curl",
        "Spider Curl",
    ],
    "Trunk": [
        "Front Plank",
        "Side Plank",
        "Dead Bug",
        "Bird Dog",
        "Hollow Hold",
        "Pallof Press",
        "Cable Chop",
        "Cable Lift",
        "Ab Wheel Rollout",
        "Stability-Ball Rollout",
        "Hanging Knee Raise",
        "Hanging Leg Raise",
        "Reverse Crunch",
        "Cable Crunch",
        "Suitcase Carry",
        "Farmer's Carry",
        "Front-Rack Carry",
        "Waiter's Carry",
        "Copenhagen Plank",
        "Back Extension Isometric",
    ],
    "Calves and grip": [
        "Standing Calf Raise",
        "Seated Calf Raise",
        "Leg Press Calf Raise",
        "Single-Leg Calf Raise",
        "Tibialis Raise",
        "Wrist Curl",
        "Reverse Wrist Curl",
        "Plate Pinch",
        "Dead Hang",
        "Fat-Grip Hold",
    ],
}


WARMUPS = [
    ("Bodyweight Squat", "Squat preparation"),
    ("Box Squat to Stand", "Squat preparation"),
    ("Squat Pry", "Squat preparation"),
    ("Goblet Squat Hold", "Squat preparation"),
    ("Ankle Rock", "Ankle mobility"),
    ("Knee-to-Wall Ankle Mobilisation", "Ankle mobility"),
    ("Calf Foam Roll", "Lower-body preparation"),
    ("Quadriceps Foam Roll", "Lower-body preparation"),
    ("Adductor Rock-Back", "Hip mobility"),
    ("Half-Kneeling Hip-Flexor Mobilisation", "Hip mobility"),
    ("90/90 Hip Switch", "Hip mobility"),
    ("Hip Airplane", "Hip control"),
    ("Supported Hip Airplane", "Hip control"),
    ("Leg Swing", "Lower-body preparation"),
    ("Lateral Leg Swing", "Lower-body preparation"),
    ("Walking Knee Hug", "Lower-body preparation"),
    ("Walking Quad Stretch", "Lower-body preparation"),
    ("World's Greatest Stretch", "Whole-body mobility"),
    ("Inchworm", "Whole-body preparation"),
    ("Bear Crawl", "Whole-body preparation"),
    ("Glute Bridge March", "Hip preparation"),
    ("Mini-Band Squat", "Hip preparation"),
    ("Scapular Push-Up", "Bench preparation"),
    ("Band Dislocate", "Shoulder mobility"),
    ("Wall Slide", "Shoulder mobility"),
    ("Serratus Wall Slide", "Bench preparation"),
    ("Band External Rotation", "Shoulder preparation"),
    ("Band Face Pull", "Shoulder preparation"),
    ("Scapular Pull-Up", "Upper-body preparation"),
    ("Bench Thoracic Extension", "Thoracic mobility"),
    ("Open Book Rotation", "Thoracic mobility"),
    ("Quadruped Thoracic Rotation", "Thoracic mobility"),
    ("Cat-Camel", "Spinal movement"),
    ("Pelvic Tilt", "Trunk control"),
    ("Crook-Lying Breathing", "Breathing preparation"),
    ("Crocodile Breathing", "Breathing preparation"),
    ("McGill Curl-Up", "Trunk preparation"),
    ("Heel-Elevated Glute Bridge", "Hinge preparation"),
    ("Dowel Hip Hinge", "Hinge preparation"),
    ("Wall Hip Hinge", "Hinge preparation"),
]


ALIASES = {
    "Competition Squat": ["Comp Squat"],
    "Competition Bench Press": ["Comp Bench", "Competition Bench"],
    "Competition Deadlift": ["Comp Deadlift"],
    "Romanian Deadlift": ["RDL"],
    "Single-Leg Romanian Deadlift": ["Single-Leg RDL"],
    "Safety-Bar Squat": ["SSB Squat", "Safety Squat Bar Squat"],
    "Close-Grip Bench Press": ["CGBP", "Close Grip Bench"],
    "Touch-and-Go Bench Press": ["Touch and Go Bench"],
    "Barbell Hip Thrust": ["Hip Thrust"],
    "45-Degree Back Extension": ["45 Degree Back Extension"],
    "Bulgarian Split Squat": ["Rear-Foot-Elevated Split Squat", "RFESS"],
    "Cable Triceps Pressdown": ["Triceps Pushdown"],
    "Farmer's Carry": ["Farmers Carry", "Farmer Walk"],
    "Pallof Press": ["Anti-Rotation Press"],
    "Knee-to-Wall Ankle Mobilisation": ["Knee to Wall"],
}


def _list_text(items: list[str]) -> list[str]:
    return items


def make_record(
    name: str,
    movement: str,
    family: str,
    category: str,
    equipment: str,
    primary: list[str],
    *,
    warmup: bool = False,
) -> dict[str, object]:
    is_main = movement in {"squat", "bench", "deadlift"}
    difficulty = (
        "advanced"
        if category == "advanced"
        else ("intermediate" if is_main else "beginner")
    )
    goal = (
        "competition skill and maximal strength"
        if category == "competition"
        else (
            "movement quality and training readiness"
            if warmup
            else f"develop {family.lower()} strength and capacity"
        )
    )
    setup = f"Select appropriate {equipment}; establish a stable, comfortable start position before beginning."
    execution = f"Perform the {name.lower()} through a controlled, pain-free range; maintain balance and finish each repetition consistently."
    if warmup:
        execution = f"Move through the {name.lower()} slowly and smoothly, using only the range you can control."
    relevance = (
        "direct"
        if category == "competition"
        else ("high" if is_main else ("none" if warmup else "moderate"))
    )
    return {
        "name": name,
        "aliases": ALIASES.get(name, []),
        "movement": movement,
        "family": family,
        "category": category,
        "equipment": equipment,
        "primary_muscles": primary,
        "secondary_muscles": ["trunk"]
        if "trunk" not in primary
        else ["hip stabilisers"],
        "goal": goal,
        "difficulty": difficulty,
        "setup": setup,
        "execution": execution,
        "coaching_cues": _list_text(
            [
                "Brace before each repetition",
                "Use a controlled range",
                "Keep the load balanced",
            ]
        ),
        "common_mistakes": _list_text(
            [
                "Using more load than can be controlled",
                "Rushing the change of direction",
            ]
        ),
        "regressions": _list_text(
            ["Reduce the load", "Shorten the range while retaining control"]
        ),
        "progressions": _list_text(
            ["Add load gradually", "Increase the controlled range or repetitions"]
        ),
        "cautions": "Stop if the movement causes sharp or worsening pain; use a suitable alternative and seek qualified assessment when needed.",
        "competition_relevance": relevance,
        "prescription_styles": [
            "sets and repetitions",
            "RPE" if not warmup else "controlled repetitions",
            "time" if warmup else "percentage for established barbell lifts",
        ],
        "rep_ranges": "1-6 reps"
        if category == "competition"
        else (
            "5-15 reps"
            if is_main
            else ("5-10 controlled reps or 20-40 seconds" if warmup else "6-20 reps")
        ),
        "warmup_suitable": warmup,
        "accessory_suitable": not is_main and not warmup,
        "active": True,
        "fatigue_rating": 1
        if warmup
        else (5 if category == "competition" else (4 if is_main else 2)),
        "default_sets": 2 if warmup else 3,
        "default_reps": "5"
        if category == "competition"
        else ("8" if is_main else ("8" if warmup else "12")),
        "default_rpe": 5.0 if warmup else 7.0,
        "default_rest_seconds": 30 if warmup else (180 if is_main else 90),
        "occurrences": 0,
    }


def accessory_equipment(name: str, fallback: str) -> str:
    """Return the most specific implement implied by an accessory name."""

    rules = (
        (("Cable", "Pulldown", "Pressdown", "Pallof"), "cable"),
        (("Machine", "Pec Deck", "Leg Press", "Leg Extension", "Leg Curl"), "machine"),
        (("Dumbbell", "Arnold", "Hammer", "Waiter's"), "dumbbell"),
        (("Barbell", "Pendlay", "Good Morning", "JM Press"), "barbell"),
        (("Band", "Monster Walk", "Spanish Squat"), "resistance band"),
        (("Sled",), "sled"),
        (("Landmine",), "landmine"),
        (("Stability-Ball",), "stability ball"),
        (("Slider",), "sliders"),
    )
    for terms, equipment in rules:
        if any(term in name for term in terms):
            return equipment
    return fallback


def build() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for name, category, equipment in SQUAT:
        records.append(
            make_record(
                name, "squat", "Squat", category, equipment, ["quadriceps", "glutes"]
            )
        )
    for name, category, equipment in BENCH:
        records.append(
            make_record(
                name, "bench", "Bench press", category, equipment, ["chest", "triceps"]
            )
        )
    for name, category, equipment in HINGE:
        records.append(
            make_record(
                name,
                "deadlift",
                "Deadlift and hinge",
                category,
                equipment,
                ["hamstrings", "glutes", "back"],
            )
        )
    equipment_by_family = {
        "Back": "cable, machine, dumbbell, barbell or bodyweight",
        "Quads": "machine, dumbbell, sled or bodyweight",
        "Hamstrings": "machine, cable or bodyweight",
        "Glutes": "cable, machine, band, dumbbell or bodyweight",
        "Shoulders": "dumbbell, cable, machine, barbell, band or bodyweight",
        "Chest": "dumbbell, cable, machine or bodyweight",
        "Triceps": "cable, dumbbell, barbell or bodyweight",
        "Biceps": "barbell, dumbbell or cable",
        "Trunk": "bodyweight, cable or free weights",
        "Calves and grip": "machine, free weights or bodyweight",
    }
    for family, names in ACCESSORIES.items():
        for name in names:
            category = (
                "unilateral"
                if any(term in name for term in ("Single-", "Split", "Lunge", "Step-"))
                else "accessory"
            )
            equipment = accessory_equipment(name, equipment_by_family[family])
            records.append(
                make_record(
                    name, "accessory", family, category, equipment, [family.lower()]
                )
            )
    for name, family in WARMUPS:
        records.append(
            make_record(
                name,
                "warmup",
                family,
                "movement preparation",
                "bodyweight, band or light implement",
                ["movement-specific musculature"],
                warmup=True,
            )
        )
    identities = [record["name"].casefold() for record in records]
    if len(records) != 276 or len(set(identities)) != len(records):
        raise RuntimeError(f"Expected 276 unique exercises, found {len(records)}")
    return records


if __name__ == "__main__":
    payload = {
        "schema_version": 2,
        "catalogue": "Traditional Strength starter exercise library",
        "language": "en-GB",
        "exercises": build(),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
