"""add division_id to subject

Revision ID: ee7174fe64d3
Revises: 0d6f352d92dd
Create Date: 2026-04-28 18:49:49.257615

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ee7174fe64d3'
down_revision = '0d6f352d92dd'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect
    bind = op.get_bind()
    existing_cols = [c['name'] for c in inspect(bind).get_columns('subject')]
    if 'division_id' not in existing_cols:
        with op.batch_alter_table('subject', schema=None) as batch_op:
            batch_op.add_column(sa.Column('division_id', sa.Integer(), nullable=True))
            batch_op.create_unique_constraint('uq_subject_name_division', ['name', 'division_id'])
            batch_op.create_foreign_key('fk_subject_division', 'division', ['division_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.drop_constraint('fk_subject_division', type_='foreignkey')
        batch_op.drop_constraint('uq_subject_name_division', type_='unique')
        batch_op.drop_column('division_id')
