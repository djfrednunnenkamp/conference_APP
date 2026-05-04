"""remove unique name constraint from subject

Revision ID: bd852907efe2
Revises: ee7174fe64d3
Create Date: 2026-04-28 18:55:26.952372

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bd852907efe2'
down_revision = 'ee7174fe64d3'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite batch mode recreates the table, dropping the unnamed UNIQUE(name) constraint.
    # The composite uq_subject_name_division is preserved via reflect + explicit definition.
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.alter_column('name', existing_type=sa.String(length=100), nullable=False)


def downgrade():
    pass
