"""Camera 引用完整性告警的敏感数据边界单元测试。"""

import logging
from uuid import UUID

from app.modules.cameras.persistence.integrity import (
    ReferenceIntegrityIssue,
    ReferenceIntegrityIssueKind,
    report_reference_integrity_issues,
)


def test_完整性报告日志只包含稳定类型和ID(caplog) -> None:
    """巡检告警接入不携带 Camera 凭据或任意记录内容。"""

    camera_id = UUID("00000000-0000-4000-8000-000000000001")
    source_id = UUID("10000000-0000-4000-8000-000000000001")
    with caplog.at_level(logging.ERROR, logger="app.modules.cameras.persistence.integrity"):
        report_reference_integrity_issues(
            (
                ReferenceIntegrityIssue(
                    kind=ReferenceIntegrityIssueKind.ORPHAN_SOURCE,
                    camera_id=camera_id,
                    source_id=source_id,
                ),
                ReferenceIntegrityIssue(
                    kind=ReferenceIntegrityIssueKind.CAMERA_WITHOUT_SOURCE,
                    camera_id=camera_id,
                    source_id=None,
                ),
            )
        )

    records = [
        record
        for record in caplog.records
        if record.name == "app.modules.cameras.persistence.integrity"
    ]
    assert len(records) == 2
    assert {record.message for record in records} == {"Camera 引用完整性异常"}
    assert {record.event for record in records} == {"camera.reference_integrity_failed"}
    assert records[0].integrity_issue_kind == "ORPHAN_SOURCE"
    assert records[0].camera_id == str(camera_id)
    assert records[0].source_id == str(source_id)
    assert records[1].integrity_issue_kind == "CAMERA_WITHOUT_SOURCE"
    assert not hasattr(records[1], "source_id")
