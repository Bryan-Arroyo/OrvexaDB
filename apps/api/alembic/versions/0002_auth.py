"""Add password rotation, sessions and login throttling."""
from alembic import op

revision = "0002_auth"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM users WHERE password_hash IS NULL OR role_id IS NULL) THEN RAISE EXCEPTION 'users require password_hash and role_id before 0002_auth'; END IF; END $$")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM user_sessions) THEN RAISE EXCEPTION 'existing sessions require controlled reauthentication before 0002_auth'; END IF; END $$")
    op.execute("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMPTZ")
    op.execute("ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN role_id SET NOT NULL")
    op.execute("ALTER TABLE user_sessions ADD COLUMN csrf_token_hash VARCHAR(64) NOT NULL")
    op.execute("ALTER TABLE user_sessions ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute("CREATE INDEX ix_user_sessions_user_id ON user_sessions(user_id)")
    op.execute("CREATE INDEX ix_user_sessions_expires_at ON user_sessions(expires_at)")
    op.execute("CREATE INDEX ix_user_sessions_token_hash ON user_sessions(token_hash)")
    op.execute("CREATE TABLE login_attempts (id UUID PRIMARY KEY, key_hmac VARCHAR(64) NOT NULL UNIQUE, window_started_at TIMESTAMPTZ NOT NULL DEFAULT now(), failure_count INTEGER NOT NULL DEFAULT 0, blocked_until TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), CONSTRAINT ck_login_attempts_failure_nonnegative CHECK (failure_count >= 0))")
    op.execute("CREATE INDEX ix_login_attempts_key_hmac ON login_attempts(key_hmac)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_login_attempts_key_hmac")
    op.execute("DROP TABLE IF EXISTS login_attempts")
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_token_hash")
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_user_id")
    op.execute("ALTER TABLE user_sessions DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE user_sessions DROP COLUMN IF EXISTS csrf_token_hash")
    op.execute("ALTER TABLE users ALTER COLUMN role_id DROP NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS must_change_password")
