"""Record the initial SQLite revision before adding domain tables."""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Mark a new database at the empty schema baseline."""


def downgrade() -> None:
    """Return to the unversioned schema."""
