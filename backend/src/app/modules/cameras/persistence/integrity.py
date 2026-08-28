"""无外键 Camera 表的只读引用完整性巡检。"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow

logger = logging.getLogger(__name__)


class ReferenceIntegrityIssueKind(StrEnum):
    """巡检可报告的稳定异常类型。"""

    ORPHAN_SOURCE = "ORPHAN_SOURCE"
    MISSING_DEFAULT_SOURCE = "MISSING_DEFAULT_SOURCE"
    DEFAULT_SOURCE_OWNED_BY_ANOTHER_CAMERA = "DEFAULT_SOURCE_OWNED_BY_ANOTHER_CAMERA"
    CAMERA_WITHOUT_SOURCE = "CAMERA_WITHOUT_SOURCE"


@dataclass(frozen=True, slots=True)
class ReferenceIntegrityIssue:
    """一条不执行自动修复的引用完整性异常。"""

    kind: ReferenceIntegrityIssueKind
    camera_id: UUID
    source_id: UUID | None


async def scan_reference_integrity(session: AsyncSession) -> tuple[ReferenceIntegrityIssue, ...]:
    """检测四类跨表异常，不锁表、不删除或修改任何记录。"""

    issues: list[ReferenceIntegrityIssue] = []

    orphan_statement = (
        select(CameraSourceRow.camera_id, CameraSourceRow.source_id)
        .outerjoin(CameraRow, CameraRow.camera_id == CameraSourceRow.camera_id)
        .where(CameraRow.camera_id.is_(None))
        .order_by(CameraSourceRow.camera_id, CameraSourceRow.source_id)
    )
    for camera_id, source_id in (await session.execute(orphan_statement)).tuples():
        issues.append(
            ReferenceIntegrityIssue(
                kind=ReferenceIntegrityIssueKind.ORPHAN_SOURCE,
                camera_id=camera_id,
                source_id=source_id,
            )
        )

    default_source = aliased(CameraSourceRow)
    missing_default_statement = (
        select(CameraRow.camera_id, CameraRow.default_preview_source_id)
        .outerjoin(
            default_source,
            default_source.source_id == CameraRow.default_preview_source_id,
        )
        .where(default_source.source_id.is_(None))
        .order_by(CameraRow.camera_id)
    )
    for camera_id, source_id in (await session.execute(missing_default_statement)).tuples():
        issues.append(
            ReferenceIntegrityIssue(
                kind=ReferenceIntegrityIssueKind.MISSING_DEFAULT_SOURCE,
                camera_id=camera_id,
                source_id=source_id,
            )
        )

    foreign_default = aliased(CameraSourceRow)
    foreign_default_statement = (
        select(CameraRow.camera_id, CameraRow.default_preview_source_id)
        .join(
            foreign_default,
            foreign_default.source_id == CameraRow.default_preview_source_id,
        )
        .where(foreign_default.camera_id != CameraRow.camera_id)
        .order_by(CameraRow.camera_id)
    )
    for camera_id, source_id in (await session.execute(foreign_default_statement)).tuples():
        issues.append(
            ReferenceIntegrityIssue(
                kind=ReferenceIntegrityIssueKind.DEFAULT_SOURCE_OWNED_BY_ANOTHER_CAMERA,
                camera_id=camera_id,
                source_id=source_id,
            )
        )

    owned_source = aliased(CameraSourceRow)
    empty_camera_statement = (
        select(CameraRow.camera_id)
        .outerjoin(owned_source, owned_source.camera_id == CameraRow.camera_id)
        .where(owned_source.source_id.is_(None))
        .order_by(CameraRow.camera_id)
    )
    for camera_id in (await session.scalars(empty_camera_statement)).all():
        issues.append(
            ReferenceIntegrityIssue(
                kind=ReferenceIntegrityIssueKind.CAMERA_WITHOUT_SOURCE,
                camera_id=camera_id,
                source_id=None,
            )
        )

    return tuple(issues)


def report_reference_integrity_issues(
    issues: tuple[ReferenceIntegrityIssue, ...],
) -> None:
    """把巡检结果接入日志告警；只记录非敏感 ID 和稳定异常类型。"""

    for issue in issues:
        logger.error(
            "Camera 引用完整性异常",
            extra={
                "event": "camera.reference_integrity_failed",
                "camera_id": str(issue.camera_id),
                "integrity_issue_kind": issue.kind.value,
                **({"source_id": str(issue.source_id)} if issue.source_id is not None else {}),
            },
        )
