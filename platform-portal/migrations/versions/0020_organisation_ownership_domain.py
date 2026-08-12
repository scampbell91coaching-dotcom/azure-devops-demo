"""Add organisation-scoped membership, invitation, and athlete ownership.

Revision ID: 0020_organisation_ownership_domain
Revises: 0019_meal_plan_delivery

This revision intentionally creates only new tables. Existing users and athletes
remain valid and can be associated with a default organisation in a later,
explicit data migration.
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_organisation_ownership_domain"
down_revision = "0019_meal_plan_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organisations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organisations_slug"),
    )
    op.create_index("ix_organisations_slug", "organisations", ["slug"], unique=True)
    op.create_index("ix_organisations_active", "organisations", ["active"])

    op.create_table(
        "organisation_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'admin', 'coach', 'support')", name="ck_organisation_memberships_role"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_organisation_memberships_status"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organisation_id", "user_id", name="uq_organisation_membership_user"),
        sa.UniqueConstraint("organisation_id", "id", name="uq_organisation_membership_scope"),
    )
    op.create_index("ix_organisation_memberships_org_status_role", "organisation_memberships", ["organisation_id", "status", "role"])

    op.create_table(
        "coach_athlete_ownerships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("coach_membership_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_coach_athlete_ownerships_status"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organisation_id", "coach_membership_id"], ["organisation_memberships.organisation_id", "organisation_memberships.id"], name="fk_ownership_coach_membership_scope", ondelete="RESTRICT"),
        sa.UniqueConstraint("organisation_id", "athlete_id", name="uq_coach_athlete_ownership_org_athlete"),
    )
    op.create_index("ix_coach_athlete_ownerships_athlete_id", "coach_athlete_ownerships", ["athlete_id"])
    op.create_index("ix_coach_athlete_ownerships_org_coach_status", "coach_athlete_ownerships", ["organisation_id", "coach_membership_id", "status"])

    op.create_table(
        "organisation_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("email_normalised", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("invited_by_membership_id", sa.Integer(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'admin', 'coach', 'support')", name="ck_organisation_invitations_role"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'revoked', 'expired')", name="ck_organisation_invitations_status"),
        sa.CheckConstraint("(status = 'accepted' AND accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL) OR (status <> 'accepted' AND accepted_at IS NULL AND accepted_by_user_id IS NULL)", name="ck_organisation_invitations_acceptance"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organisation_id", "invited_by_membership_id"], ["organisation_memberships.organisation_id", "organisation_memberships.id"], name="fk_invitation_inviter_membership_scope", ondelete="RESTRICT"),
        sa.UniqueConstraint("token_digest", name="uq_organisation_invitations_token_digest"),
    )
    op.create_index("ix_organisation_invitations_expires_at", "organisation_invitations", ["expires_at"])
    op.create_index("ix_organisation_invitations_org_status_email", "organisation_invitations", ["organisation_id", "status", "email_normalised"])
    op.create_index("uq_organisation_invitations_pending_email", "organisation_invitations", ["organisation_id", "email_normalised"], unique=True, sqlite_where=sa.text("status = 'pending'"), postgresql_where=sa.text("status = 'pending'"))


def downgrade():
    op.drop_table("organisation_invitations")
    op.drop_table("coach_athlete_ownerships")
    op.drop_table("organisation_memberships")
    op.drop_table("organisations")
