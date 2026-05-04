"""add order to grade_group

Revision ID: 187d278f64a3
Revises: bacd66cb2c45
Create Date: 2026-04-29 18:09:17.723290

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '187d278f64a3'
down_revision = 'bacd66cb2c45'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('grade_group', schema=None) as batch_op:
        batch_op.add_column(sa.Column('order', sa.Integer(), nullable=False,
                                      server_default='0'))


def downgrade():
    with op.batch_alter_table('grade_group', schema=None) as batch_op:
        batch_op.drop_column('order')
