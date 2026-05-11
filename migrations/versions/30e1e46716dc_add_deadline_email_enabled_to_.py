"""add_deadline_email_enabled_to_conference_event

Revision ID: 30e1e46716dc
Revises: 21a850fd57a9
Create Date: 2026-05-11 14:02:07.385120

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '30e1e46716dc'
down_revision = '21a850fd57a9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conference_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deadline_email_enabled', sa.Boolean(), server_default='1', nullable=False))


def downgrade():
    with op.batch_alter_table('conference_event', schema=None) as batch_op:
        batch_op.drop_column('deadline_email_enabled')
