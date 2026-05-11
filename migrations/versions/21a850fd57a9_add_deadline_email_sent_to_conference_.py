"""add deadline_email_sent to conference_event

Revision ID: 21a850fd57a9
Revises: b2c3d4e5f6a7
Create Date: 2026-05-11 13:50:34.317212

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '21a850fd57a9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conference_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deadline_email_sent', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('conference_event', schema=None) as batch_op:
        batch_op.drop_column('deadline_email_sent')
