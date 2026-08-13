"""Add the organisation-scoped SaaS billing foundation.

Revision ID: 0021_saas_billing_foundation
Revises: 0020_organisation_ownership_domain
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_saas_billing_foundation"
down_revision = "0020_organisation_ownership_domain"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subscription_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("plan_identifier", sa.String(100), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("provider_customer_id", sa.String(255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("state IN ('trialing', 'active', 'past_due', 'cancelled', 'incomplete')", name="ck_subscription_accounts_state"),
        sa.CheckConstraint("(provider IS NULL AND provider_customer_id IS NULL AND provider_subscription_id IS NULL) OR (provider IS NOT NULL AND provider_customer_id IS NOT NULL AND provider_subscription_id IS NOT NULL)", name="ck_subscription_accounts_provider_identity"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organisation_id"),
        sa.UniqueConstraint("provider", "provider_customer_id", name="uq_subscription_provider_customer"),
        sa.UniqueConstraint("provider", "provider_subscription_id", name="uq_subscription_provider_subscription"),
    )
    op.create_index("ix_subscription_accounts_organisation_id", "subscription_accounts", ["organisation_id"], unique=True)
    op.create_index("ix_subscription_accounts_plan_identifier", "subscription_accounts", ["plan_identifier"])
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('processing', 'processed', 'failed')", name="ck_billing_webhook_events_status"),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_webhook_provider_event"),
    )


def downgrade():
    op.drop_table("billing_webhook_events")
    op.drop_table("subscription_accounts")
