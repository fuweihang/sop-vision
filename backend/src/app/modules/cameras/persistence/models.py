"""Camera 配置表的无外键 SQLAlchemy 映射。"""

from datetime import datetime
from ipaddress import IPv4Address
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CameraRow(Base):
    """Camera 聚合根的持久化记录；跨表引用由 Repository 维护。"""

    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint("family(ip_address) = 4", name="ip_address_ipv4"),
        CheckConstraint(
            "rtsp_port >= 1 AND rtsp_port <= 65535",
            name="rtsp_port_range",
        ),
    )

    camera_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_address: Mapped[IPv4Address] = mapped_column(postgresql.INET(), nullable=False)
    rtsp_port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password: Mapped[str] = mapped_column(String(512), nullable=False)
    default_preview_source_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CameraSourceRow(Base):
    """CameraSource 持久化记录；``camera_id`` 是无外键的逻辑引用。"""

    __tablename__ = "camera_sources"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        UniqueConstraint(
            "camera_id",
            "url_suffix",
            name="uq_camera_sources_camera_id_url_suffix",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "camera_id",
            "sort_order",
            name="uq_camera_sources_camera_id_sort_order",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_camera_sources_camera_id", "camera_id"),
    )

    source_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True)
    camera_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url_suffix: Mapped[str] = mapped_column(String(1024, collation="C"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
