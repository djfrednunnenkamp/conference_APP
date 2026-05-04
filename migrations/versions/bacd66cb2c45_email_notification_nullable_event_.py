"""email_notification_nullable_event_string_type

Revision ID: bacd66cb2c45
Revises: bd852907efe2
Create Date: 2026-04-29 08:10:10.614929

SQLite cannot drop unnamed FK constraints via batch_alter, so we rebuild
the email_notification table with raw SQL (same approach used for subject).
The subject FK change is also a no-op in SQLite so we skip it here.
"""
from alembic import op
import sqlalchemy as sa


revision = 'bacd66cb2c45'
down_revision = 'bd852907efe2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # ── Rebuild email_notification with nullable event_id + VARCHAR(32) type ──
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS email_notification_new (
            id           INTEGER PRIMARY KEY,
            event_id     INTEGER REFERENCES conference_event(id) ON DELETE SET NULL,
            recipient_id INTEGER NOT NULL REFERENCES user(id),
            sent_at      DATETIME NOT NULL,
            type         VARCHAR(32) NOT NULL
        )
    """))
    bind.execute(sa.text("""
        INSERT INTO email_notification_new (id, event_id, recipient_id, sent_at, type)
        SELECT id, event_id, recipient_id, sent_at, type
        FROM email_notification
    """))
    bind.execute(sa.text("DROP TABLE email_notification"))
    bind.execute(sa.text("ALTER TABLE email_notification_new RENAME TO email_notification"))


def downgrade():
    # Reverting to nullable=False would break any null rows; best-effort only.
    pass
