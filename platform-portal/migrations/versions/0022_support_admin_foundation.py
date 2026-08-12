"""Add the fail-closed support administration foundation.

Revision ID: 0022_support_admin_foundation
Revises: 0021_saas_billing_foundation
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_support_admin_foundation"
down_revision = "0021_saas_billing_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "support_principals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("subject"),
    )
    op.create_index("ix_support_principals_subject", "support_principals", ["subject"], unique=True)
    op.create_table(
        "support_capability_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["principal_id"], ["support_principals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("principal_id", "capability", name="uq_support_capability_grant"),
    )
    op.create_index("ix_support_capability_grants_principal_id", "support_capability_grants", ["principal_id"])
    op.create_table(
        "support_access_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.Column("tenant_ref", sa.String(255), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("reference", sa.String(255), nullable=False),
        sa.Column("target_account_ref", sa.String(255), nullable=True),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.CheckConstraint("visibility IN ('tenant', 'internal')", name="ck_support_event_visibility"),
        sa.ForeignKeyConstraint(["principal_id"], ["support_principals.id"], ondelete="RESTRICT"),
    )
    for column in ("principal_id", "tenant_ref", "action", "reference", "occurred_at"):
        op.create_index(f"ix_support_access_events_{column}", "support_access_events", [column])
    op.create_table(
        "support_delegations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.Column("tenant_ref", sa.String(255), nullable=False),
        sa.Column("target_account_ref", sa.String(255), nullable=False),
        sa.Column("start_event_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("expires_at > started_at", name="ck_support_delegation_period"),
        sa.ForeignKeyConstraint(["principal_id"], ["support_principals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["start_event_id"], ["support_access_events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("start_event_id"),
    )
    for column in ("principal_id", "tenant_ref", "expires_at"):
        op.create_index(f"ix_support_delegations_{column}", "support_delegations", [column])


def downgrade():
    op.drop_table("support_delegations")
    op.drop_table("support_access_events")
    op.drop_table("support_capability_grants")
    op.drop_table("support_principals")
