"""Baseline the current coaching schema.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "athletes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("instagram", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("bodyweight_kg", sa.Float(), nullable=True),
        sa.Column("weight_class", sa.String(length=40), nullable=True),
        sa.Column("federation", sa.String(length=80), nullable=True),
        sa.Column("next_competition", sa.String(length=160), nullable=True),
        sa.Column("coach_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_athletes_created_at", "athletes", ["created_at"])
    op.create_index("ix_athletes_email", "athletes", ["email"], unique=True)
    op.create_index("ix_athletes_status", "athletes", ["status"])

    op.create_table(
        "coaching_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("instagram", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("bodyweight_kg", sa.Float(), nullable=True),
        sa.Column("years_training", sa.Float(), nullable=True),
        sa.Column("squat_kg", sa.Float(), nullable=True),
        sa.Column("bench_kg", sa.Float(), nullable=True),
        sa.Column("deadlift_kg", sa.Float(), nullable=True),
        sa.Column("next_competition", sa.String(length=160), nullable=True),
        sa.Column("current_program", sa.Text(), nullable=True),
        sa.Column("previous_coaching", sa.Text(), nullable=True),
        sa.Column("primary_goal", sa.Text(), nullable=False),
        sa.Column("biggest_problem", sa.Text(), nullable=False),
        sa.Column("injury_history", sa.Text(), nullable=True),
        sa.Column("coaching_expectations", sa.Text(), nullable=False),
        sa.Column("training_days", sa.Integer(), nullable=True),
        sa.Column("video_feedback_ready", sa.Boolean(), nullable=False),
        sa.Column("communication_ready", sa.Boolean(), nullable=False),
        sa.Column("minimum_term_ready", sa.Boolean(), nullable=False),
        sa.Column("referral_source", sa.String(length=160), nullable=True),
        sa.Column("anything_else", sa.Text(), nullable=True),
        sa.Column("privacy_consent", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_coaching_applications_email", "coaching_applications", ["email"]
    )
    op.create_index(
        "ix_coaching_applications_status", "coaching_applications", ["status"]
    )
    op.create_index(
        "ix_coaching_applications_submitted_at",
        "coaching_applications",
        ["submitted_at"],
    )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("movement", sa.String(length=40), nullable=False),
        sa.Column("family", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("variation", sa.String(length=120), nullable=True),
        sa.Column("equipment", sa.String(length=120), nullable=True),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=True),
        sa.Column("primary_muscles", sa.String(length=255), nullable=True),
        sa.Column("secondary_muscles", sa.String(length=255), nullable=True),
        sa.Column("fatigue_rating", sa.Integer(), nullable=False),
        sa.Column("default_sets", sa.Integer(), nullable=True),
        sa.Column("default_reps", sa.String(length=40), nullable=True),
        sa.Column("default_rpe", sa.Float(), nullable=True),
        sa.Column("default_rest_seconds", sa.Integer(), nullable=True),
        sa.Column("coaching_cues", sa.Text(), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exercises_active", "exercises", ["active"])
    op.create_index("ix_exercises_family", "exercises", ["family"])
    op.create_index("ix_exercises_movement", "exercises", ["movement"])
    op.create_index("ix_exercises_name", "exercises", ["name"], unique=True)

    op.create_table(
        "day_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_day_templates_code", "day_templates", ["code"], unique=True)

    op.create_table(
        "lead_captures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("source_slug", sa.String(length=120), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_captures_created_at", "lead_captures", ["created_at"])
    op.create_index("ix_lead_captures_email", "lead_captures", ["email"])
    op.create_index("ix_lead_captures_source_slug", "lead_captures", ["source_slug"])

    op.create_table(
        "platform_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("platform_score", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.String(length=3), nullable=False),
        sa.Column("health_latency_seconds", sa.Float(), nullable=False),
        sa.Column("ready_nodes", sa.Integer(), nullable=False),
        sa.Column("total_nodes", sa.Integer(), nullable=False),
        sa.Column("ready_replicas", sa.Integer(), nullable=False),
        sa.Column("desired_replicas", sa.Integer(), nullable=False),
        sa.Column("container_restarts", sa.Integer(), nullable=False),
        sa.Column("argo_sync_status", sa.String(length=32), nullable=False),
        sa.Column("argo_health_status", sa.String(length=32), nullable=False),
        sa.Column("security_pass_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("git_revision", sa.String(length=64), nullable=False),
        sa.Column("git_branch", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_snapshots_recorded_at", "platform_snapshots", ["recorded_at"]
    )

    op.create_table(
        "athlete_checkin_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("training_enabled", sa.Boolean(), nullable=False),
        sa.Column("nutrition_enabled", sa.Boolean(), nullable=False),
        sa.Column("workflow_active", sa.Boolean(), nullable=False),
        sa.Column("checkin_day", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_athlete_checkin_settings_athlete_id",
        "athlete_checkin_settings",
        ["athlete_id"],
        unique=True,
    )

    op.create_table(
        "day_template_exercises",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.String(length=40), nullable=True),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["day_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_day_template_exercises_exercise_id",
        "day_template_exercises",
        ["exercise_id"],
    )
    op.create_index(
        "ix_day_template_exercises_template_id",
        "day_template_exercises",
        ["template_id"],
    )

    op.create_table(
        "nutrition_checkins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("bodyweight_kg", sa.Float(), nullable=True),
        sa.Column("average_calories", sa.Integer(), nullable=True),
        sa.Column("average_protein_g", sa.Integer(), nullable=True),
        sa.Column("average_steps", sa.Integer(), nullable=True),
        sa.Column("nutrition_adherence", sa.Integer(), nullable=False),
        sa.Column("hunger", sa.Integer(), nullable=False),
        sa.Column("energy", sa.Integer(), nullable=False),
        sa.Column("sleep_quality", sa.Integer(), nullable=False),
        sa.Column("stress", sa.Integer(), nullable=False),
        sa.Column("digestion", sa.Integer(), nullable=False),
        sa.Column("training_performance", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Text(), nullable=True),
        sa.Column("challenges", sa.Text(), nullable=True),
        sa.Column("upcoming_events", sa.Text(), nullable=True),
        sa.Column("questions", sa.Text(), nullable=True),
        sa.Column("coach_response", sa.Text(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_nutrition_checkins_athlete_id", "nutrition_checkins", ["athlete_id"]
    )
    op.create_index(
        "ix_nutrition_checkins_reviewed", "nutrition_checkins", ["reviewed"]
    )
    op.create_index(
        "ix_nutrition_checkins_submitted_at", "nutrition_checkins", ["submitted_at"]
    )

    op.create_table(
        "training_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_blocks_athlete_id", "training_blocks", ["athlete_id"])
    op.create_index("ix_training_blocks_status", "training_blocks", ["status"])

    op.create_table(
        "weekly_checkins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("week_ending", sa.Date(), nullable=False),
        sa.Column("training_included", sa.Boolean(), nullable=False),
        sa.Column("nutrition_included", sa.Boolean(), nullable=False),
        sa.Column("training_adherence", sa.Integer(), nullable=True),
        sa.Column("fatigue", sa.Integer(), nullable=True),
        sa.Column("recovery", sa.Integer(), nullable=True),
        sa.Column("motivation", sa.Integer(), nullable=True),
        sa.Column("pain_present", sa.Boolean(), nullable=True),
        sa.Column("training_notes", sa.Text(), nullable=True),
        sa.Column("average_bodyweight_kg", sa.Float(), nullable=True),
        sa.Column("calories_average", sa.Integer(), nullable=True),
        sa.Column("protein_average_g", sa.Integer(), nullable=True),
        sa.Column("steps_average", sa.Integer(), nullable=True),
        sa.Column("nutrition_adherence", sa.Integer(), nullable=True),
        sa.Column("nutrition_notes", sa.Text(), nullable=True),
        sa.Column("sleep_quality", sa.Integer(), nullable=True),
        sa.Column("stress", sa.Integer(), nullable=True),
        sa.Column("general_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("coach_notes", sa.Text(), nullable=True),
        sa.Column("coach_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weekly_checkins_athlete_id", "weekly_checkins", ["athlete_id"])

    op.create_table(
        "training_weeks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["block_id"], ["training_blocks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_weeks_block_id", "training_weeks", ["block_id"])

    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("day_label", sa.String(length=80), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["week_id"], ["training_weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_sessions_week_id", "training_sessions", ["week_id"])

    op.create_table(
        "exercise_prescriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_name", sa.String(length=160), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prescription_type", sa.String(length=40), nullable=True),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.String(length=40), nullable=True),
        sa.Column("reps_min", sa.Integer(), nullable=True),
        sa.Column("reps_max", sa.Integer(), nullable=True),
        sa.Column("load_kg", sa.Float(), nullable=True),
        sa.Column("load_cap_kg", sa.Float(), nullable=True),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column("rpe_cap", sa.Float(), nullable=True),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_rpe", sa.Float(), nullable=True),
        sa.Column("target_load_kg", sa.Float(), nullable=True),
        sa.Column("amrap", sa.Boolean(), nullable=True),
        sa.Column("tempo", sa.String(length=40), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["training_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_exercise_prescriptions_session_id",
        "exercise_prescriptions",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_table("exercise_prescriptions")
    op.drop_table("training_sessions")
    op.drop_table("training_weeks")
    op.drop_table("weekly_checkins")
    op.drop_table("training_blocks")
    op.drop_table("nutrition_checkins")
    op.drop_table("day_template_exercises")
    op.drop_table("athlete_checkin_settings")
    op.drop_table("platform_snapshots")
    op.drop_table("lead_captures")
    op.drop_table("day_templates")
    op.drop_table("exercises")
    op.drop_table("coaching_applications")
    op.drop_table("athletes")
