"""create worker task parameters

Revision ID: 20260821_0001
Revises:
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260821_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_task_parameters",
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("worker_type", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(task_id) <> ''", name="ck_worker_task_id_nonempty"),
        sa.CheckConstraint("btrim(worker_type) <> ''", name="ck_worker_type_nonempty"),
        sa.CheckConstraint(
            "jsonb_typeof(config) = 'object'", name="ck_worker_config_object"
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.execute(
        """
        CREATE FUNCTION set_worker_task_parameters_updated_at()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_worker_task_parameters_updated_at
        BEFORE UPDATE ON worker_task_parameters
        FOR EACH ROW EXECUTE FUNCTION set_worker_task_parameters_updated_at()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_worker_task_parameters_updated_at "
        "ON worker_task_parameters"
    )
    op.drop_table("worker_task_parameters")
    op.execute("DROP FUNCTION IF EXISTS set_worker_task_parameters_updated_at()")
