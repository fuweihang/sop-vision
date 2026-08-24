"""Fake 与 PostgreSQL Camera Repository 共用的最小聚合行为契约。"""

from app.modules.cameras.application import CameraListCriteria, CameraRepository
from app.modules.cameras.domain import Camera
from tests.modules.cameras.builders import uuid4_from_index


async def assert_camera_repository_contract(
    repository: CameraRepository,
    original: Camera,
    updated: Camera,
) -> None:
    """验证同一端口的新增、读取、完整保存、列表、计数与删除语义。"""

    missing_id = uuid4_from_index(999_999)
    assert await repository.get(missing_id) is None
    await repository.add(original)
    assert await repository.get(original.camera_id) == original

    await repository.save(updated)
    assert await repository.get(original.camera_id) == updated
    assert await repository.count(CameraListCriteria()) == 1
    assert await repository.list(CameraListCriteria(), 1, 100) == (updated,)
    assert await repository.list(CameraListCriteria(), 2, 100) == ()

    assert await repository.delete(original.camera_id) == updated
    assert await repository.delete(original.camera_id) is None
    assert await repository.get(original.camera_id) is None
