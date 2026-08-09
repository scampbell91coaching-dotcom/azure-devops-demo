"""Persist reusable assigned session warm-ups and athlete snapshots.

Revision ID: 0014_warmup_integration
Revises: 0013_accessory_intelligence
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_warmup_integration"
down_revision = "0013_accessory_intelligence"
branch_labels = None
depends_on = None


def _instruction_columns(*, snapshot: bool = False):
    return [
        sa.Column("phase", sa.Integer(), nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer()), sa.Column("duration_seconds", sa.Integer()),
        sa.Column("percentage", sa.Float()), sa.Column("load_kg", sa.Float()),
        sa.Column("rest_seconds", sa.Integer()), sa.Column("notes", sa.Text()),
    ]


def upgrade():
    op.create_table("warmup_protocols", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("stable_key", sa.String(80), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.Text()), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")), sa.Column("created_at", sa.DateTime(), nullable=False), sa.CheckConstraint("version > 0", name="ck_warmup_protocol_version"), sa.UniqueConstraint("stable_key", "version", name="uq_warmup_protocol_version"))
    op.create_table("warmup_protocol_steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("warmup_protocols.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), *_instruction_columns(), sa.CheckConstraint("position > 0", name="ck_warmup_protocol_step_position"), sa.CheckConstraint("phase IN (10, 20, 30, 40)", name="ck_warmup_protocol_step_phase"), sa.CheckConstraint("kind IN ('reps', 'duration', 'barbell')", name="ck_warmup_protocol_step_kind"), sa.CheckConstraint("sets > 0", name="ck_warmup_protocol_step_sets"), sa.UniqueConstraint("protocol_id", "position", name="uq_warmup_protocol_step_position"))
    op.create_index("ix_warmup_protocol_steps_protocol_id", "warmup_protocol_steps", ["protocol_id"])
    op.create_table("warmup_assignments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("warmup_protocols.id", ondelete="RESTRICT"), nullable=False), sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False), sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id", ondelete="RESTRICT"), nullable=False), sa.Column("assigned_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")), sa.Column("reason", sa.String(500), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("session_id", "protocol_id", name="uq_warmup_assignment_session_protocol"))
    for column in ("protocol_id", "athlete_id", "session_id"): op.create_index(f"ix_warmup_assignments_{column}", "warmup_assignments", [column])
    op.create_table("warmup_overrides", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False), sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id", ondelete="RESTRICT"), nullable=False), sa.Column("action", sa.String(20), nullable=False), sa.Column("target_key", sa.String(120)), sa.Column("phase", sa.Integer()), sa.Column("name", sa.String(160)), sa.Column("kind", sa.String(20)), sa.Column("sets", sa.Integer()), sa.Column("reps", sa.Integer()), sa.Column("duration_seconds", sa.Integer()), sa.Column("percentage", sa.Float()), sa.Column("load_kg", sa.Float()), sa.Column("rest_seconds", sa.Integer()), sa.Column("notes", sa.Text()), sa.Column("reason", sa.String(500), nullable=False), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")), sa.Column("created_at", sa.DateTime(), nullable=False), sa.CheckConstraint("action IN ('remove', 'append')", name="ck_warmup_override_action"), sa.CheckConstraint("phase IS NULL OR phase IN (10, 20, 30, 40)", name="ck_warmup_override_phase"), sa.CheckConstraint("kind IS NULL OR kind IN ('reps', 'duration', 'barbell')", name="ck_warmup_override_kind"))
    for column in ("athlete_id", "session_id"): op.create_index(f"ix_warmup_overrides_{column}", "warmup_overrides", [column])
    op.create_table("warmup_plan_snapshots", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False), sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id", ondelete="RESTRICT"), nullable=False), sa.Column("resolved_at", sa.DateTime(), nullable=False), sa.Column("resolver_version", sa.String(20), nullable=False), sa.UniqueConstraint("athlete_id", "session_id", name="uq_warmup_snapshot_session"))
    for column in ("athlete_id", "session_id"): op.create_index(f"ix_warmup_plan_snapshots_{column}", "warmup_plan_snapshots", [column])
    op.create_table("warmup_plan_snapshot_steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("warmup_plan_snapshots.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), *_instruction_columns(), sa.Column("source_type", sa.String(30), nullable=False), sa.Column("source_key", sa.String(120), nullable=False), sa.Column("source_version", sa.Integer()), sa.Column("reason", sa.String(500)), sa.UniqueConstraint("snapshot_id", "position", name="uq_warmup_snapshot_step_position"))
    op.create_index("ix_warmup_plan_snapshot_steps_snapshot_id", "warmup_plan_snapshot_steps", ["snapshot_id"])


def downgrade():
    for table in ("warmup_plan_snapshot_steps", "warmup_plan_snapshots", "warmup_overrides", "warmup_assignments", "warmup_protocol_steps", "warmup_protocols"):
        op.drop_table(table)
