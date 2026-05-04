"""add event_sector and event_sector_teacher tables

Revision ID: c4e7a12f9b03
Revises: 187d278f64a3
Create Date: 2026-04-30 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e7a12f9b03'
down_revision = '187d278f64a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_sector',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('division_id', sa.Integer(), nullable=True),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('slot_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('break_minutes', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['conference_event.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['division_id'], ['division.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'division_id', name='uq_event_sector'),
    )
    op.create_table(
        'event_sector_teacher',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sector_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('slot_duration_minutes', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['sector_id'], ['event_sector.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['teacher_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sector_id', 'teacher_id', name='uq_sector_teacher'),
    )


def downgrade():
    op.drop_table('event_sector_teacher')
    op.drop_table('event_sector')
