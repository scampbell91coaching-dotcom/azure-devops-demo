"""Add secure athlete account lifecycle tokens.

Revision ID: 0012_athlete_accounts
Revises: 0010_programming_v7
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_athlete_accounts"
down_revision = "0010_programming_v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=512),
            nullable=True,
        )
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivery_state", sa.String(length=24), nullable=False),
        sa.Column("delivery_detail", sa.String(length=500), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('invitation', 'password_reset')",
            name="ck_account_tokens_purpose",
        ),
        sa.CheckConstraint(
            "delivery_state IN ('pending', 'sent', 'not_configured', 'failed')",
            name="ck_account_tokens_delivery_state",
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_tokens_athlete_id", "account_tokens", ["athlete_id"])
    op.create_index("ix_account_tokens_expires_at", "account_tokens", ["expires_at"])
    op.create_index("ix_account_tokens_purpose", "account_tokens", ["purpose"])
    op.create_index(
        "ix_account_tokens_token_digest", "account_tokens", ["token_digest"], unique=True
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_account_tokens_user_id", table_name="account_tokens")
    op.drop_index("ix_account_tokens_token_digest", table_name="account_tokens")
    op.drop_index("ix_account_tokens_purpose", table_name="account_tokens")
    op.drop_index("ix_account_tokens_expires_at", table_name="account_tokens")
    op.drop_index("ix_account_tokens_athlete_id", table_name="account_tokens")
    op.drop_table("account_tokens")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=512),
            nullable=False,
        )
