"""使用行锁维护无外键 Camera 引用完整性的专用 Repository。"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cameras.persistence.errors import (
    CameraNotFoundError,
    DefaultSourceReplacementRequiredError,
    InvalidCameraAggregateError,
    LastCameraSourceError,
    SourceNotOwnedByCameraError,
)
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow


class CameraPersistenceRepository:
    """封装所有跨 ``cameras`` 与 ``camera_sources`` 的写入。

    Repository 只执行 ``flush``，不提交或回滚。调用方必须为一个业务用例提供同一个
    ``AsyncSession`` 和事务。除新聚合外，所有写入都先锁 Camera，再锁 Source。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_aggregate(
        self,
        camera: CameraRow,
        sources: Sequence[CameraSourceRow],
    ) -> None:
        """写入完整新聚合，并在 flush 后再次确认默认源归属。"""

        if not sources:
            raise InvalidCameraAggregateError("Camera 必须至少包含一路 Source。")
        if any(source.camera_id != camera.camera_id for source in sources):
            raise InvalidCameraAggregateError("全部 Source 必须属于待创建的 Camera。")

        source_ids = {source.source_id for source in sources}
        if len(source_ids) != len(sources):
            raise InvalidCameraAggregateError("同一聚合内的 Source ID 不得重复。")
        if camera.default_preview_source_id not in source_ids:
            raise InvalidCameraAggregateError("默认 Source 必须属于待创建的 Camera。")

        self._session.add(camera)
        self._session.add_all(sources)
        await self._session.flush()

        default_source = await self._get_owned_source_for_update(
            camera.camera_id,
            camera.default_preview_source_id,
        )
        if default_source is None:
            raise InvalidCameraAggregateError("持久化后的默认 Source 不属于当前 Camera。")

    async def get_camera_for_update(self, camera_id: UUID) -> CameraRow:
        """锁定 Camera；所有聚合更新和删除都以此作为第一个锁。"""

        statement = select(CameraRow).where(CameraRow.camera_id == camera_id).with_for_update()
        camera = (await self._session.scalars(statement)).one_or_none()
        if camera is None:
            raise CameraNotFoundError
        return camera

    async def get_source_for_update(
        self,
        camera_id: UUID,
        source_id: UUID,
    ) -> CameraSourceRow:
        """按 Camera → Source 的顺序加锁，供后续完整更新复用。"""

        await self.get_camera_for_update(camera_id)
        source = await self._get_owned_source_for_update(camera_id, source_id)
        if source is None:
            raise SourceNotOwnedByCameraError
        return source

    async def add_source(self, source: CameraSourceRow) -> None:
        """确认并锁定父 Camera 后新增 Source。"""

        await self.get_camera_for_update(source.camera_id)
        self._session.add(source)
        await self._session.flush()

    async def set_default_source(self, camera_id: UUID, source_id: UUID) -> None:
        """锁定 Camera 和目标 Source 后切换默认源。"""

        camera = await self.get_camera_for_update(camera_id)
        source = await self._get_owned_source_for_update(camera_id, source_id)
        if source is None:
            raise SourceNotOwnedByCameraError
        camera.default_preview_source_id = source.source_id
        await self._session.flush()

    async def delete_source(
        self,
        camera_id: UUID,
        source_id: UUID,
        *,
        replacement_default_source_id: UUID | None = None,
    ) -> None:
        """删除一路 Source，同时保护最后一路和当前默认源。"""

        camera = await self.get_camera_for_update(camera_id)
        statement = (
            select(CameraSourceRow.source_id)
            .where(CameraSourceRow.camera_id == camera_id)
            .order_by(CameraSourceRow.source_id)
            .with_for_update()
        )
        source_ids = tuple((await self._session.scalars(statement)).all())
        if source_id not in source_ids:
            raise SourceNotOwnedByCameraError
        if len(source_ids) == 1:
            raise LastCameraSourceError

        if camera.default_preview_source_id == source_id:
            if (
                replacement_default_source_id is None
                or replacement_default_source_id == source_id
                or replacement_default_source_id not in source_ids
            ):
                raise DefaultSourceReplacementRequiredError
            camera.default_preview_source_id = replacement_default_source_id

        await self._session.execute(
            delete(CameraSourceRow).where(
                CameraSourceRow.camera_id == camera_id,
                CameraSourceRow.source_id == source_id,
            )
        )
        await self._session.flush()

    async def delete_camera(self, camera_id: UUID) -> None:
        """先锁 Camera，再显式删除全部 Source 和 Camera。"""

        await self.get_camera_for_update(camera_id)
        await self._session.execute(
            delete(CameraSourceRow).where(CameraSourceRow.camera_id == camera_id)
        )
        await self._session.execute(delete(CameraRow).where(CameraRow.camera_id == camera_id))
        await self._session.flush()

    async def _get_owned_source_for_update(
        self,
        camera_id: UUID,
        source_id: UUID,
    ) -> CameraSourceRow | None:
        statement = (
            select(CameraSourceRow)
            .where(
                CameraSourceRow.camera_id == camera_id,
                CameraSourceRow.source_id == source_id,
            )
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()
