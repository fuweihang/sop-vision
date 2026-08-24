"""创建无外键 Camera 关系模型。

修订 ID：0002_camera_schema
前置修订：0001_database_runtime
创建日期：2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_camera_schema"
down_revision: str | Sequence[str] | None = "0001_database_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.Column("rtsp_port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password", sa.String(length=512), nullable=False),
        sa.Column(
            "default_preview_source_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "family(ip_address) = 4",
            name=op.f("ck_cameras_ip_address_ipv4"),
        ),
        sa.CheckConstraint(
            "rtsp_port >= 1 AND rtsp_port <= 65535",
            name=op.f("ck_cameras_rtsp_port_range"),
        ),
        sa.PrimaryKeyConstraint("camera_id", name=op.f("pk_cameras")),
    )
    op.create_table(
        "camera_sources",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "url_suffix",
            sa.String(length=1024, collation="C"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sort_order >= 0",
            name=op.f("ck_camera_sources_sort_order_non_negative"),
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_camera_sources")),
        sa.UniqueConstraint(
            "camera_id",
            "sort_order",
            name=op.f("uq_camera_sources_camera_id_sort_order"),
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "camera_id",
            "url_suffix",
            name=op.f("uq_camera_sources_camera_id_url_suffix"),
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        op.f("ix_camera_sources_camera_id"),
        "camera_sources",
        ["camera_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_camera_sources_camera_id"), table_name="camera_sources")
    op.drop_table("camera_sources")
    op.drop_table("cameras")
