"""Build the reviewed Traditional Strength practical exercise catalogue.

Run from the repository root. The compact source lists make duplicate review
practical; the emitted JSON is the production import asset.
"""

from __future__ import annotations

import json
import re
import unicodedata
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
    "Upper back": [
        "Chest-Supported T-Bar Row",
        "Wide-Grip Cable Row",
        "High Row",
        "Single-Arm Machine Row",
        "Kelso Shrug",
        "Dumbbell Pullover",
        "Cable Pullover",
        "Prone Rear-Delt Row",
    ],
    "Lower back": [
        "Bird-Dog Row",
        "Roman-Chair Back Extension",
        "Sorensen Hold",
        "Machine Back Extension",
        "Weighted Back Extension",
        "Quadruped Rock-Back",
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
    "GPP and carries": [
        "Heavy Sled Push",
        "Forward Sled Drag",
        "Lateral Sled Drag",
        "Sled Rope Pull",
        "Trap-Bar Carry",
        "Double-Kettlebell Front-Rack Carry",
        "Sandbag Bear-Hug Carry",
        "Overhead Carry",
        "Uneven Farmer Carry",
        "Plate Carry",
    ],
    "Conditioning": [
        "Air Bike Intervals",
        "Rowing Ergometer Intervals",
        "Ski Ergometer Intervals",
        "Incline Treadmill Walk",
        "Prowler Sprint",
        "Battle Rope Waves",
        "Kettlebell Swing Intervals",
        "Medicine-Ball Slam",
    ],
    "Strongman": [
        "Log Clean and Press",
        "Axle Clean and Press",
        "Push Press",
        "Sandbag to Shoulder",
        "Sandbag Load",
        "Atlas Stone Load",
        "Yoke Walk",
        "Frame Carry",
        "Keg Carry",
        "Tire Flip",
        "Sled Arm-Over-Arm Pull",
        "Zercher Carry",
    ],
    "Rehabilitation regressions": [
        "Supported Split Squat",
        "Sit-to-Stand",
        "Low Box Step-Up",
        "Assisted Calf Raise",
        "Isometric Calf Raise",
        "Short-Lever Copenhagen Plank",
        "Banded Terminal Knee Extension",
        "Wall Push-Up",
        "Supported Single-Leg Romanian Deadlift",
        "Isometric Hamstring Bridge",
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
    ("Supine 90/90 Breathing", "Breathing and position"),
    ("Hook-Lying Heel-Dig Breathing", "Breathing and position"),
    ("Half-Kneeling Breathing", "Breathing and position"),
    ("All-Fours Breathing", "Breathing and position"),
    ("Wall-Supported Reach", "Breathing and position"),
    ("Dead-Bug Breathing", "Breathing and position"),
    ("Bench Lat Stretch", "Upper-body mobility"),
    ("Prayer Stretch", "Upper-body mobility"),
    ("Wrist Rock", "Wrist preparation"),
    ("Banded Ankle Dorsiflexion", "Ankle mobility"),
    ("Prying Cossack Squat", "Hip mobility"),
    ("Hamstring Sweep", "Lower-body preparation"),
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
    "Bulgarian Split Squat": ["Rear-Foot-Elevated Split Squat", "RFESS"],
    "Cable Triceps Pressdown": ["Triceps Pushdown"],
    "Farmer's Carry": ["Farmers Carry", "Farmer Walk"],
    "Pallof Press": ["Anti-Rotation Press"],
    "Knee-to-Wall Ankle Mobilisation": ["Knee to Wall"],
    "Air Bike Intervals": ["Assault Bike", "Fan Bike"],
    "Rowing Ergometer Intervals": ["Rower Intervals", "Row Erg Intervals"],
    "Ski Ergometer Intervals": ["SkiErg Intervals", "Ski Erg"],
    "Log Clean and Press": ["Log Press"],
    "Axle Clean and Press": ["Axle Press"],
    "Atlas Stone Load": ["Stone Load", "Atlas Stones"],
    "Yoke Walk": ["Yoke Carry"],
    "Banded Terminal Knee Extension": ["TKE", "Band TKE"],
    "Supine 90/90 Breathing": ["90 90 Breathing"],
    "Double-Kettlebell Front-Rack Carry": ["Double KB Front Rack Carry"],
    "Roman-Chair Back Extension": ["Roman Chair Extension"],
}


MOVEMENT_KNOWLEDGE = {
    "squat": {
        "setup": "Set the bar securely, take an even grip and stance, then brace before unlocking the knees and hips.",
        "execution": "Descend with the load balanced over the mid-foot, reach the intended depth under control, then drive evenly to standing.",
        "coaching_cues": [
            "Brace before you descend",
            "Keep pressure through the whole foot",
            "Drive the floor away",
        ],
        "common_mistakes": [
            "Losing mid-foot balance",
            "Relaxing the trunk at the bottom",
        ],
        "regressions": [
            "Reduce the load",
            "Use a goblet squat to practise balance and depth",
        ],
        "progressions": [
            "Add load while preserving depth",
            "Use a pause to strengthen the bottom position",
        ],
        "cautions": "Use safeties set just below the intended depth. Stop if pain changes the movement or prevents a stable, controlled repetition.",
    },
    "bench": {
        "setup": "Set the rack height, lie with eyes under the bar, plant the feet and secure an even grip before unracking with straight arms.",
        "execution": "Lower the bar to a repeatable touch point with the upper back and feet braced, then press to a controlled lockout.",
        "coaching_cues": [
            "Set the upper back",
            "Keep the wrists over the elbows",
            "Press back towards the rack",
        ],
        "common_mistakes": [
            "Losing upper-back tension",
            "Allowing the wrists to fold behind the bar",
        ],
        "regressions": ["Reduce the load", "Use a push-up or machine chest press"],
        "progressions": [
            "Add load without changing the touch point",
            "Add a deliberate pause on the chest",
        ],
        "cautions": "Use a competent spotter or correctly positioned safeties. Stop if pain prevents a stable touch or press path.",
    },
    "deadlift": {
        "setup": "Centre the feet under the bar, take a secure grip, brace the trunk and remove slack without moving the bar forwards.",
        "execution": "Push through the floor as the bar stays close, stand tall without leaning back, then return it under control.",
        "coaching_cues": [
            "Brace and take out the slack",
            "Keep the bar close",
            "Push the floor away",
        ],
        "common_mistakes": [
            "Jerking the bar from the floor",
            "Letting the bar drift away from the legs",
        ],
        "regressions": ["Reduce the load", "Raise the start position on blocks"],
        "progressions": [
            "Add load while keeping a consistent start",
            "Add a pause just off the floor",
        ],
        "cautions": "Choose a load that allows a braced, repeatable start and controlled return. Stop if pain changes the pulling position.",
    },
}


FAMILY_KNOWLEDGE = {
    "Back": (
        "Set the implement and brace the trunk before initiating with the shoulder blades and elbows.",
        "Pull through a controlled range, pause briefly in the shortened position, then return without losing trunk position.",
        ["Lead with the elbows", "Keep the neck relaxed", "Control the return"],
        ["Using momentum", "Shrugging instead of pulling through the target range"],
    ),
    "Quads": (
        "Set the machine or stance so the working foot is stable and the knee can track freely.",
        "Bend and extend the knee through a controlled range while keeping pressure distributed across the foot.",
        [
            "Keep the whole foot planted",
            "Let the knee track with the toes",
            "Control the lowering phase",
        ],
        ["Bouncing out of the bottom", "Allowing the knee to collapse inwards"],
    ),
    "Hamstrings": (
        "Adjust the pad or body position so the hips remain supported and the knee moves freely.",
        "Flex the knee or hinge under control, pause in the shortened position where appropriate, then return slowly.",
        ["Keep the hips still", "Move under control", "Own the lengthened position"],
        ["Lifting the hips to finish", "Rushing the return"],
    ),
    "Glutes": (
        "Adopt a stable stance and align the resistance with the intended direction of hip movement.",
        "Move from the hip without rotating the pelvis, pause briefly, then return under control.",
        ["Keep the pelvis level", "Move from the hip", "Finish without overextending"],
        ["Rotating to create range", "Using momentum"],
    ),
    "Shoulders": (
        "Choose a light, controllable load and set the ribs and shoulder blades before moving the arms.",
        "Move through the available shoulder range without shrugging or using trunk momentum, then lower slowly.",
        ["Keep the ribs stacked", "Move the arms smoothly", "Keep the neck relaxed"],
        ["Shrugging the load up", "Swinging through the trunk"],
    ),
    "Chest": (
        "Set a stable hand and body position with the shoulders controlled and the resistance aligned across the chest.",
        "Press or bring the arms together through a controlled range, then return without the shoulders rolling forwards.",
        ["Keep the shoulders controlled", "Move smoothly", "Control the stretch"],
        ["Forcing excessive depth", "Losing body position"],
    ),
    "Triceps": (
        "Set the upper arm in a stable position and choose a load that permits full elbow control.",
        "Extend the elbow without moving the shoulder excessively, then return slowly to the start.",
        [
            "Keep the upper arm quiet",
            "Reach a controlled lockout",
            "Control the return",
        ],
        ["Swinging the upper arm", "Using trunk momentum"],
    ),
    "Biceps": (
        "Stand or sit with the trunk braced, wrists neutral and upper arms in the intended position.",
        "Flex the elbow without swinging, squeeze briefly, then lower through a controlled range.",
        ["Keep the upper arm still", "Keep the wrist stacked", "Lower slowly"],
        ["Swinging the torso", "Letting the wrist fold back"],
    ),
    "Trunk": (
        "Choose a stable base and set the ribs over the pelvis before applying resistance.",
        "Maintain the intended trunk position while breathing and moving only through the prescribed joints.",
        [
            "Keep the ribs stacked",
            "Breathe behind the brace",
            "Stop before position changes",
        ],
        [
            "Holding the breath unnecessarily",
            "Using a range that breaks trunk position",
        ],
    ),
    "Calves and grip": (
        "Set the implement securely and use a stable stance or supported seated position.",
        "Move through the available range or hold with steady tension, avoiding bouncing and unnecessary joint movement.",
        [
            "Use the full controlled range",
            "Keep pressure even",
            "Hold without compensating",
        ],
        ["Bouncing repetitions", "Letting the implement slip out of position"],
    ),
    "Upper back": (
        "Set the support or cable height, brace the trunk and let the shoulder blades reach without losing position.",
        "Draw the elbows or implement towards the torso, pause briefly, then return to the start under control.",
        ["Reach then row", "Keep the chest supported", "Lower under control"],
        ["Jerking from the start", "Shortening the return"],
    ),
    "Lower back": (
        "Set the support so the hips can move freely and establish a gently braced trunk before starting.",
        "Move through the hips or hold the chosen trunk position while maintaining steady breathing and control.",
        ["Brace before moving", "Use the hips", "Stop before position changes"],
        ["Chasing excessive range", "Losing control to finish a repetition"],
    ),
    "GPP and carries": (
        "Clear the route, secure the load and establish a tall, braced start before moving.",
        "Walk or drive with short purposeful steps, keeping the implement controlled until the set is complete.",
        ["Brace before the first step", "Take quick controlled steps", "Finish under control"],
        ["Starting before the route is clear", "Letting posture collapse as fatigue rises"],
    ),
    "Conditioning": (
        "Check the machine or training area, select a sustainable starting effort and keep the work interval unobstructed.",
        "Build to the prescribed effort, maintain repeatable mechanics, then reduce speed deliberately for recovery.",
        ["Start under control", "Keep each interval repeatable", "Recover deliberately"],
        ["Sprinting the first interval blindly", "Allowing technique to deteriorate"],
    ),
    "Strongman": (
        "Inspect the implement, clear the working area and take a balanced grip or contact position before applying force.",
        "Move the implement with a braced trunk and deliberate footwork, completing each phase before changing direction.",
        ["Secure the implement", "Brace before each phase", "Use deliberate footwork"],
        ["Rushing the pickup", "Continuing after control is lost"],
    ),
    "Rehabilitation regressions": (
        "Arrange stable support and choose a range that can be completed smoothly without compensating.",
        "Move slowly through the selected range or hold the position while breathing, then return with the same control.",
        ["Use support as needed", "Keep the repetition smooth", "Build range gradually"],
        ["Forcing range", "Removing support before control is established"],
    ),
}


RECORD_OVERRIDES = {
    "Competition Squat": {
        "aliases": ["Comp Squat", "Powerlifting Squat"],
        "setup": "Set the hooks below shoulder height and safeties just below depth. Centre the bar across the upper back, take an even grip, brace, stand it clear and take the minimum steps into the chosen stance.",
        "execution": "After the start command in competition practice, unlock knees and hips together, descend until the hip crease passes below the top of the knee, then stand to locked knees before reracking on command.",
        "coaching_cues": [
            "Brace before the descent",
            "Stay balanced over mid-foot",
            "Drive the floor away",
        ],
        "common_mistakes": [
            "Rushing the walkout",
            "Cutting depth",
            "Letting the chest and hips rise at different rates",
        ],
        "regressions": ["High-bar back squat", "Goblet squat"],
        "progressions": [
            "Paused competition squat",
            "Competition squat with command practice",
        ],
        "rep_ranges": "1-6 reps; mostly 1-4 near competition",
    },
    "Competition Bench Press": {
        "aliases": ["Comp Bench", "Competition Bench"],
        "setup": "Set the hooks so the bar can be unracked without losing shoulder position. Plant the feet, keep the required contact points on the bench, take an even legal grip and receive a controlled hand-off if used.",
        "execution": "Hold the bar motionless at straight arms, lower to the chest, pause until the press command in competition practice, then press to locked elbows and wait for the rack command.",
        "coaching_cues": [
            "Set the upper back",
            "Meet the bar with the chest",
            "Press back to lockout",
        ],
        "common_mistakes": [
            "Softening during the pause",
            "Uneven elbow lockout",
            "Lifting a required contact point",
        ],
        "regressions": ["Paused bench press without commands", "Push-up"],
        "progressions": [
            "Long-pause bench press",
            "Competition bench with full commands",
        ],
        "rep_ranges": "1-8 reps; mostly 1-5 near competition",
    },
    "Competition Deadlift": {
        "aliases": ["Comp Deadlift", "Powerlifting Deadlift"],
        "setup": "Centre the feet beneath the bar in the chosen legal stance, take a secure grip, brace and remove slack while keeping the bar still before the attempt begins.",
        "execution": "Lift in one continuous effort until knees and hips are locked and the shoulders are upright, hold the bar motionless, then return it with both hands after the down command in competition practice.",
        "coaching_cues": [
            "Take out the slack",
            "Push the floor away",
            "Stand tall and hold",
        ],
        "common_mistakes": [
            "Jerking the bar from the floor",
            "Losing the bar forwards",
            "Lowering before the command",
        ],
        "regressions": ["Block pull", "Trap-bar deadlift"],
        "progressions": [
            "Paused deadlift",
            "Competition deadlift with command practice",
        ],
        "rep_ranges": "1-6 reps; mostly 1-4 near competition",
    },
    "Barbell Row": {
        "aliases": ["Bent-Over Barbell Row"],
        "coaching_cues": [
            "Brace the torso",
            "Pull towards the lower ribs",
            "Lower to straight arms",
        ],
        "regressions": ["Chest-supported dumbbell row"],
        "progressions": ["Paused barbell row"],
    },
    "Lat Pulldown": {
        "aliases": ["Cable Lat Pulldown"],
        "coaching_cues": [
            "Set the shoulders down",
            "Drive the elbows towards the ribs",
            "Control to straight arms",
        ],
        "regressions": ["Single-arm lat pulldown"],
        "progressions": ["Pull-up"],
    },
    "Leg Press": {
        "coaching_cues": [
            "Keep the pelvis supported",
            "Track knees with toes",
            "Press through the whole foot",
        ],
        "regressions": ["Reduce the load or range"],
        "progressions": ["Single-leg press"],
    },
    "Seated Leg Curl": {
        "coaching_cues": [
            "Keep the hips against the pad",
            "Curl through the heel",
            "Control the return",
        ],
        "regressions": ["Banded leg curl"],
        "progressions": ["Single-leg curl"],
    },
    "Face Pull": {
        "coaching_cues": [
            "Pull towards eye level",
            "Finish with hands apart",
            "Keep the ribs stacked",
        ],
        "regressions": ["Band face pull"],
        "progressions": ["Add a controlled external rotation"],
    },
    "Cable Triceps Pressdown": {
        "aliases": ["Triceps Pushdown"],
        "coaching_cues": [
            "Pin the upper arms",
            "Extend without leaning",
            "Control to full elbow bend",
        ],
        "regressions": ["Use a lighter cable setting"],
        "progressions": ["Single-arm pressdown"],
    },
    "Pallof Press": {
        "aliases": ["Anti-Rotation Press"],
        "coaching_cues": [
            "Keep ribs over pelvis",
            "Press straight forwards",
            "Resist turning towards the cable",
        ],
        "regressions": ["Use a wider stance or lighter band"],
        "progressions": ["Half-kneeling Pallof press"],
    },
    "Dowel Hip Hinge": {
        "equipment": "dowel",
        "setup": "Stand tall with a dowel touching the head, upper back and tailbone; soften the knees and brace lightly.",
        "execution": "Push the hips backwards while maintaining all three dowel contact points, then squeeze the glutes to stand.",
        "coaching_cues": [
            "Keep three points of contact",
            "Send the hips back",
            "Stand tall",
        ],
        "common_mistakes": ["Squatting instead of hinging", "Losing dowel contact"],
        "regressions": ["Wall hip hinge"],
        "progressions": ["Light kettlebell Romanian deadlift"],
    },
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
    setup = f"Set up the {equipment} securely and establish a stable position that allows the intended joints to move freely."
    execution = f"Perform the {name.lower()} through a controlled range, pause where appropriate, then return without using momentum."
    cues = [
        "Set a stable start position",
        "Move through a controlled range",
        "Keep the load balanced",
    ]
    mistakes = [
        "Using momentum to create range",
        "Choosing more load than can be controlled",
    ]
    regressions = ["Reduce the load", "Shorten the range while retaining control"]
    progressions = [
        "Add load gradually",
        "Increase the controlled range or repetitions",
    ]
    cautions = "Set the equipment securely and stop if discomfort changes the intended movement or prevents a controlled repetition."
    uses_movement_template = (
        (movement == "squat" and "bar" in equipment.casefold())
        or (movement == "bench" and "barbell" in equipment.casefold())
        or (
            movement == "deadlift"
            and any(term in name for term in ("Deadlift", "Block Pull", "Rack Pull"))
            and "bar" in equipment.casefold()
        )
    )
    if uses_movement_template:
        knowledge = MOVEMENT_KNOWLEDGE[movement]
        setup = knowledge["setup"]
        execution = knowledge["execution"]
        cues = knowledge["coaching_cues"]
        mistakes = knowledge["common_mistakes"]
        regressions = knowledge["regressions"]
        progressions = knowledge["progressions"]
        cautions = knowledge["cautions"]
    elif family in FAMILY_KNOWLEDGE:
        setup, execution, cues, mistakes = FAMILY_KNOWLEDGE[family]
    if warmup:
        setup = f"Use a clear space and arrange any light equipment needed for the {name.lower()}; begin in a relaxed, stable position."
        execution = f"Move through the {name.lower()} slowly for controlled repetitions, exploring only the range that can be kept smooth and repeatable."
        cues = ["Move slowly", "Keep breathing", "Use only a controllable range"]
        mistakes = ["Forcing extra range", "Rushing through repetitions"]
        regressions = ["Use support or reduce the range"]
        progressions = ["Increase the range gradually while retaining control"]
        cautions = "This is a preparation drill, not a loaded stretch. Reduce the range or stop if the movement becomes painful or uncontrolled."
    relevance = (
        "direct"
        if category == "competition"
        else ("high" if is_main else ("none" if warmup else "moderate"))
    )
    record = {
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
        "coaching_cues": _list_text(cues),
        "common_mistakes": _list_text(mistakes),
        "regressions": _list_text(regressions),
        "progressions": _list_text(progressions),
        "cautions": cautions,
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
    record.update(RECORD_OVERRIDES.get(name, {}))
    return record


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
        "Upper back": "cable, machine, dumbbell or bodyweight",
        "Lower back": "bodyweight, bench or machine",
        "GPP and carries": "sled, kettlebells, sandbag or free weights",
        "Conditioning": "conditioning machine or training implement",
        "Strongman": "strongman implement",
        "Rehabilitation regressions": "bodyweight, band or light resistance",
    }
    for family, names in ACCESSORIES.items():
        for name in names:
            category = "accessory"
            if family == "Conditioning":
                category = "conditioning"
            elif family == "GPP and carries":
                category = "gpp"
            elif family == "Strongman":
                category = "strongman"
            elif family == "Rehabilitation regressions":
                category = "regression"
            elif any(term in name for term in ("Single-", "Split", "Lunge", "Step-")):
                category = "unilateral"
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
    identity_owners: dict[str, str] = {}
    for record in records:
        name = str(record["name"])
        for value in [name, *record["aliases"]]:
            normalised = unicodedata.normalize("NFKD", str(value)).casefold()
            identity = re.sub(r"[^a-z0-9]+", " ", normalised).strip()
            owner = identity_owners.setdefault(identity, name)
            if owner != name:
                raise RuntimeError(
                    f"Exercise identity {value!r} is shared by {owner!r} and {name!r}"
                )
    if len(records) < 300:
        raise RuntimeError(f"Expected at least 300 exercises, found {len(records)}")
    return records


if __name__ == "__main__":
    payload = {
        "schema_version": 4,
        "catalogue": "Traditional Strength practical exercise library",
        "language": "en-GB",
        "exercises": build(),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
