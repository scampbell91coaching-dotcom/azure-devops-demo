"""Add minimal Organisation invitation delivery and supersession state."""
import sqlalchemy as sa
from alembic import op
revision = "0023_organisation_invitation_delivery"
down_revision = "0022_support_admin_foundation"
branch_labels = depends_on = None

def upgrade():
    with op.batch_alter_table("organisation_invitations") as batch:
        batch.add_column(sa.Column("delivery_state", sa.String(20), nullable=False, server_default="pending"))
        batch.add_column(sa.Column("delivery_detail", sa.String(500)))
        batch.add_column(sa.Column("delivered_at", sa.DateTime()))
        batch.drop_constraint("ck_organisation_invitations_status", type_="check")
        batch.create_check_constraint("ck_organisation_invitations_status", "status IN ('pending', 'accepted', 'revoked', 'expired', 'superseded')")
        batch.create_check_constraint("ck_organisation_invitations_delivery_state", "delivery_state IN ('pending', 'sent', 'not_configured', 'failed')")

def downgrade():
    with op.batch_alter_table("organisation_invitations") as batch:
        batch.drop_constraint("ck_organisation_invitations_delivery_state", type_="check")
        batch.drop_constraint("ck_organisation_invitations_status", type_="check")
        batch.create_check_constraint("ck_organisation_invitations_status", "status IN ('pending', 'accepted', 'revoked', 'expired')")
        batch.drop_column("delivered_at"); batch.drop_column("delivery_detail"); batch.drop_column("delivery_state")
