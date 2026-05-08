"""add teacher breaks

Revision ID: a1b2c3d4e5f6
Revises: d3d2870019b1
Create Date: 2026-05-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'd3d2870019b1'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_break column to slot table
    with op.batch_alter_table('slot', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_break', sa.Boolean(),
                                      nullable=False, server_default='0'))

    # Create teacher_break table
    op.create_table(
        'teacher_break',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('day_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(['teacher_id'], ['user.id']),
        sa.ForeignKeyConstraint(['day_id'], ['conference_day.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('teacher_id', 'day_id', 'start_time', name='uq_teacher_break'),
    )


def downgrade():
    op.drop_table('teacher_break')

    with op.batch_alter_table('slot', schema=None) as batch_op:
        batch_op.drop_column('is_break')
