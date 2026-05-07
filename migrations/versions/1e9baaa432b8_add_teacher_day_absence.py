"""add teacher_day_absence

Revision ID: 1e9baaa432b8
Revises: c4e7a12f9b03
Create Date: 2026-05-07 09:52:23.867478

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e9baaa432b8'
down_revision = 'c4e7a12f9b03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('teacher_day_absence',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day_id', sa.Integer(), nullable=False),
    sa.Column('teacher_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['day_id'], ['conference_day.id'], ),
    sa.ForeignKeyConstraint(['teacher_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('day_id', 'teacher_id')
    )


def downgrade():
    op.drop_table('teacher_day_absence')
