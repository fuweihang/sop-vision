"""Camera 无外键 ORM metadata 契约测试。"""

import logging
from ipaddress import IPv4Address
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.modules.cameras.persistence.integrity import (
    ReferenceIntegrityIssue,
    ReferenceIntegrityIssueKind,
    report_reference_integrity_issues,
)
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow
from tests.modules.cameras.constants import CAMERA_LEAK_SENTINEL


def test_camera_tables_have_no_foreign_keys() -> None:
    """逻辑引用列不得因 ORM 改动重新生成外键。"""

    assert not CameraRow.__table__.foreign_keys
    assert not CameraSourceRow.__table__.foreign_keys


def test_camera_constraint_and_index_names_are_stable() -> None:
    """Repository 错误映射和迁移审查依赖稳定名称。"""

    camera_checks = {
        constraint.name
        for constraint in CameraRow.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    source_uniques = {
        constraint.name
        for constraint in CameraSourceRow.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert camera_checks == {
        "ck_cameras_ip_address_ipv4",
        "ck_cameras_rtsp_port_range",
    }
    assert source_uniques == {
        "uq_camera_sources_camera_id_sort_order",
        "uq_camera_sources_camera_id_url_suffix",
    }
    assert {index.name for index in CameraSourceRow.__table__.indexes} == {
        "ix_camera_sources_camera_id"
    }


def test_source_unique_constraints_are_initially_deferred() -> None:
    """Source 后缀交换和重排可以在事务提交前暂时经过重复中间态。"""

    unique_constraints = [
        constraint
        for constraint in CameraSourceRow.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert unique_constraints
    assert all(constraint.deferrable is True for constraint in unique_constraints)
    assert all(constraint.initially == "DEFERRED" for constraint in unique_constraints)


@pytest.mark.sensitive_data
def test_camera_row_repr_does_not_expose_password() -> None:
    """默认 ORM repr 不能泄露 Camera 凭据。"""

    camera = CameraRow(
        camera_id=UUID("00000000-0000-4000-8000-000000000001"),
        name="Camera",
        ip_address=IPv4Address("192.0.2.10"),
        rtsp_port=554,
        username="operator",
        password=CAMERA_LEAK_SENTINEL,
        default_preview_source_id=UUID("10000000-0000-4000-8000-000000000001"),
    )

    assert CAMERA_LEAK_SENTINEL not in repr(camera)


def test_integrity_report_logs_only_stable_kind_and_ids(caplog) -> None:
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
