"""add secretary role

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Alter user.role enum to include 'secretary' (SQLite: recreate via batch_alter)
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('role',
            existing_type=sa.Enum('admin', 'teacher', 'student', 'guardian'),
            type_=sa.Enum('admin', 'teacher', 'student', 'guardian', 'secretary'),
            existing_nullable=False)

    # Create secretary_division table
    op.create_table(
        'secretary_division',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('secretary_id', sa.Integer(), nullable=False),
        sa.Column('division_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['secretary_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['division_id'], ['division.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('secretary_id', 'division_id', name='uq_secretary_division'),
    )


def downgrade():
    op.drop_table('secretary_division')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('role',
            existing_type=sa.Enum('admin', 'teacher', 'student', 'guardian', 'secretary'),
            type_=sa.Enum('admin', 'teacher', 'student', 'guardian'),
            existing_nullable=False)
