"""add allow_duplicate_teacher_booking

Revision ID: d3d2870019b1
Revises: 1e9baaa432b8
Create Date: 2026-05-08 09:18:15.248454

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3d2870019b1'
down_revision = '1e9baaa432b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conference_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allow_duplicate_teacher_booking', sa.Boolean(),
                                      nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('conference_event', schema=None) as batch_op:
        batch_op.drop_column('allow_duplicate_teacher_booking')
