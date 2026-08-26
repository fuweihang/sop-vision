"""Cameras handler 占位生命周期门禁的独立回归测试。"""

import pytest

from scripts import check_camera_placeholders as placeholder_gate
from scripts.check_camera_placeholders import GateMode, check_camera_placeholders


async def _implemented_handler() -> None:
    return None


async def _pure_placeholder_handler() -> None:
    raise NotImplementedError


async def _mixed_placeholder_handler() -> None:
    # 条件不可达并不重要；AST 门禁必须发现完整实现里任何残留的占位异常。
    if False:  # pragma: no cover
        raise NotImplementedError


def test_foundation_allows_incremental_replacement_but_mvp_rejects_remaining_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """功能切片可逐个交付，但普通绿色 CI 不能被误当作 MVP 发布通过。"""

    monkeypatch.setattr(
        placeholder_gate,
        "CAMERA_HANDLERS",
        (_implemented_handler, _pure_placeholder_handler),
    )

    report = check_camera_placeholders(GateMode.FOUNDATION)
    assert report.placeholders == ("_pure_placeholder_handler",)
    assert not report.invalid_handlers

    with pytest.raises(RuntimeError, match="MVP 发布禁止残留占位 handler"):
        check_camera_placeholders(GateMode.MVP)


def test_foundation_rejects_implemented_handler_with_hidden_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """夹带在分支中的 NotImplementedError 不能绕过纯占位限制。"""

    monkeypatch.setattr(
        placeholder_gate,
        "CAMERA_HANDLERS",
        (_mixed_placeholder_handler,),
    )

    with pytest.raises(RuntimeError, match="混入了非纯占位逻辑"):
        check_camera_placeholders(GateMode.FOUNDATION)
