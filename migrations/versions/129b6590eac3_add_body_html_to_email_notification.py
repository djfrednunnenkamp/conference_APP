"""add_body_html_to_email_notification

Revision ID: 129b6590eac3
Revises: 30e1e46716dc
Create Date: 2026-05-12 09:18:13.185947

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '129b6590eac3'
down_revision = '30e1e46716dc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('email_notification', schema=None) as batch_op:
        batch_op.add_column(sa.Column('body_html', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('email_notification', schema=None) as batch_op:
        batch_op.drop_column('body_html')
