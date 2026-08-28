"""使用 SQLAlchemy AsyncSession 读写 Camera 及其全部 Source。"""

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select, true
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.cameras.application.errors import (
    CameraNotFoundError,
    CameraPersistenceOperationError,
)
from app.modules.cameras.application.ports import (
    CameraListCriteria,
    validate_camera_list_pagination,
)
from app.modules.cameras.domain import Camera, CameraId, SourceId
from app.modules.cameras.persistence.constraints import translate_integrity_error
from app.modules.cameras.persistence.mapper import (
    camera_to_rows,
    rows_to_camera,
    source_to_row,
    update_camera_row,
    update_source_row,
)
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow


class SQLAlchemyCameraRepository:
    """Camera Repository 的唯一生产实现。

    对外方法始终把一个 Camera 和它的全部 Source 当成一个整体，不提供单独修改某条 Source
    的入口。更新和删除已有 Camera 时，先锁 Camera 记录，再锁它的 Source 记录；所有并发
    写入使用相同顺序，可以减少互相等待形成死锁的风险。

    本类只把修改写入当前 Session 并执行 ``flush``，不会调用 ``commit``。最终提交由应用
    服务通过 Unit of Work 决定，因此一个业务操作中的其他数据库修改可以一起成功或回滚。
    """

    def __init__(self, session: AsyncSession) -> None:
        """保存当前请求使用的 Session；Repository 不创建也不关闭它。"""

        self._session = session

    async def add(self, camera: Camera) -> None:
        """新增一个 Camera 及其全部 Source，但不提交事务。

        Camera 对象正常情况下已经保证至少有一路 Source、Source ID 不重复并且默认 Source 属于
        当前 Camera。写库前仍做一次轻量检查，是为了防止 Mapper 或未来服务端代码的错误把
        两张无外键关联的表写成互相对不上的状态。

        ``flush`` 会立即执行 INSERT 并触发数据库规则检查，但其他事务仍看不到这些数据，
        直到 Unit of Work 显式提交。
        """

        camera_row, source_rows = camera_to_rows(camera)
        if (
            not source_rows
            or any(source.camera_id != camera.camera_id for source in source_rows)
            or len({source.source_id for source in source_rows}) != len(source_rows)
            or camera.default_preview_source_id not in {source.source_id for source in source_rows}
        ):
            # 这不是用户输入校验；命中表示服务端准备写入的数据已经自相矛盾。
            raise CameraPersistenceOperationError

        try:
            self._session.add(camera_row)
            self._session.add_all(source_rows)
            # flush 让后续查询能读到本事务刚写入的数据，同时不会提前提交整个业务操作。
            await self._session.flush()

            # 数据库没有外键替我们保证默认 Source 属于当前 Camera，所以写入后再次按
            # camera_id + source_id 查询。加锁还能避免提交前这条 Source 被并发修改。
            default_source = await self._get_owned_source_for_update(
                camera.camera_id,
                camera.default_preview_source_id,
            )
            if default_source is None:
                await self._rollback_after_failure()
                raise CameraPersistenceOperationError
        except IntegrityError as error:
            await self._rollback_after_failure()
            raise translate_integrity_error(error) from error
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error

    async def save(self, camera: Camera) -> None:
        """用完整新配置更新已有 Camera，但不提交事务。

        本方法先锁住数据库中的 Camera 和全部旧 Source，再按 Source ID 比较新旧集合：新配置
        没有的旧 Source 会被删除，仍存在的会被更新，新增 ID 会插入。调用方必须传入完整
        Camera，不能只传一条 Source 的局部变化。

        如果 Camera 已被另一个请求删除，会抛出 ``CameraNotFoundError``。如果新增 Source ID
        已被其他 Camera 使用，则以数据库操作错误失败，不能把那条 Source 改为当前 Camera
        所有。
        """

        try:
            # 先取得数据库当前状态并加锁，后面的差异计算才不会基于过期数据继续写入。
            camera_row, locked_sources = await self._lock_aggregate(camera.camera_id)
            existing_by_id = {row.source_id: row for row in locked_sources}
            incoming_by_id = {source.source_id: source for source in camera.sources}

            # 正常 Camera 对象不会出现重复 Source ID 或错误 camera_id；这里防御服务端对象被
            # 非预期方式构造，避免后面的字典覆盖重复项并静默丢数据。
            if len(incoming_by_id) != len(camera.sources) or any(
                source.camera_id != camera.camera_id for source in camera.sources
            ):
                raise CameraPersistenceOperationError

            # 只查询“本次新增”的 ID。如果数据库已存在同 ID Source，说明它属于别的 Camera；
            # Source 主键全局唯一，不能把已有记录当成本 Camera 的新增项。
            new_ids = tuple(incoming_by_id.keys() - existing_by_id.keys())
            if new_ids:
                known_ids = set(
                    (
                        await self._session.scalars(
                            select(CameraSourceRow.source_id).where(
                                CameraSourceRow.source_id.in_(new_ids)
                            )
                        )
                    ).all()
                )
                if known_ids:
                    raise CameraPersistenceOperationError

            # 先处理数据库已有 Source：完整新配置中缺失的删除，仍存在的更新可变字段。
            for source_id, row in existing_by_id.items():
                source = incoming_by_id.get(source_id)
                if source is None:
                    await self._session.delete(row)
                else:
                    update_source_row(row, source)

            # 再插入全新的 Source；具体字段复制集中在 Mapper，避免此处重复列清单。
            for source_id in new_ids:
                self._session.add(source_to_row(incoming_by_id[source_id]))

            update_camera_row(camera_row, camera)
            # 数据库会在事务提交时最终检查 Source 后缀和顺序是否重复，因此一次完整更新可以
            # 直接交换两个 Source 的值。真正的重复可能在这里或 commit 时报告，两处都会转换
            # 为相同的 Camera 应用错误。
            await self._session.flush()

            # Source 集合已经增删完成，此时重新确认新的默认 Source 仍在当前 Camera 中。
            default_source = await self._get_owned_source_for_update(
                camera.camera_id,
                camera.default_preview_source_id,
            )
            if default_source is None:
                await self._rollback_after_failure()
                raise CameraPersistenceOperationError
        except IntegrityError as error:
            await self._rollback_after_failure()
            raise translate_integrity_error(error) from error
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error

    async def get(self, camera_id: CameraId, for_update: bool = False) -> Camera | None:
        """读取一个 Camera 和它的全部 Source，找不到时返回 ``None``。

        普通读取不加锁。``for_update=True`` 用于随后准备修改同一 Camera 的业务，它会按照
        Camera → Source 的统一顺序加行锁，让并发写入等待当前事务结束。无论是否加锁，都会
        在 Session 有效期内把全部 Source 查出，不依赖 SQLAlchemy 的延迟加载。
        """

        try:
            if for_update:
                camera_row, _ = await self._lock_aggregate_or_none(camera_id)
            else:
                statement = select(CameraRow).where(CameraRow.camera_id == camera_id)
                camera_row = (await self._session.scalars(statement)).one_or_none()
            source_rows = (
                () if camera_row is None else await self._read_sources_in_domain_order((camera_id,))
            )
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error
        if camera_row is None:
            return None
        return rows_to_camera(camera_row, source_rows)

    async def list(
        self,
        criteria: CameraListCriteria,
        page: int,
        page_size: int,
    ) -> tuple[Camera, ...]:
        """搜索并分页读取 Camera，同时一次批量读取这一页的全部 Source。

        第一条查询只取当前页 Camera，并固定按创建时间、Camera ID 排序。第二条查询用这些
        Camera ID 一次取回全部 Source。这样不会为页面中的每个 Camera 各发一条 Source 查询，
        也不会在 Session 关闭后才尝试读取关联数据。
        """

        offset = validate_camera_list_pagination(page, page_size)
        try:
            statement = (
                select(CameraRow)
                .where(_camera_search_expression(criteria))
                .order_by(CameraRow.created_at.asc(), CameraRow.camera_id.asc())
                .offset(offset)
                .limit(page_size)
            )
            camera_rows = tuple((await self._session.scalars(statement)).all())
            camera_ids = tuple(row.camera_id for row in camera_rows)
            # 空页面无需执行带空 IN 条件的第二条查询。
            source_rows = (
                () if not camera_ids else await self._read_sources_in_domain_order(camera_ids)
            )
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error
        if not camera_rows:
            return ()

        # 批量查询得到的 Source 先按 camera_id 分组，再为每条记录重建完整 Camera 对象。
        sources_by_camera: defaultdict[CameraId, list[CameraSourceRow]] = defaultdict(list)
        for row in source_rows:
            sources_by_camera[row.camera_id].append(row)
        return tuple(rows_to_camera(row, sources_by_camera[row.camera_id]) for row in camera_rows)

    async def count(self, criteria: CameraListCriteria) -> int:
        """返回符合搜索条件的 Camera 总数，不加载 Camera 或 Source 的完整字段。"""

        try:
            statement = (
                select(func.count())
                .select_from(CameraRow)
                .where(_camera_search_expression(criteria))
            )
            total = await self._session.scalar(statement)
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error
        return 0 if total is None else total

    async def delete(self, camera_id: CameraId) -> Camera | None:
        """删除 Camera 及其全部 Source，并返回删除前的完整 Camera。

        返回值供应用服务在数据库提交成功后清理 MediaMTX 资源。读取和删除在同一组行锁内
        完成，所以返回的是本次删除真正针对的最新数据库内容。这里只 ``flush``，调用方仍可
        在后续业务失败时通过 Unit of Work 完整恢复 Camera 和全部 Source。
        """

        try:
            camera_row, _ = await self._lock_aggregate_or_none(camera_id)
            source_rows = (
                () if camera_row is None else await self._read_sources_in_domain_order((camera_id,))
            )
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error
        if camera_row is None:
            return None

        # 加锁时按 source_id 保证所有写操作使用相同锁顺序；重建时另按 sort_order 读取，
        # 因为 Camera 对象还需要检查 Source 顺序是否从 0 开始且连续。
        deleted_camera = rows_to_camera(camera_row, source_rows)
        try:
            # 两张表没有级联外键，必须先显式删除子 Source，再删除 Camera 本身。
            await self._session.execute(
                delete(CameraSourceRow).where(CameraSourceRow.camera_id == camera_id)
            )
            await self._session.delete(camera_row)
            await self._session.flush()
        except IntegrityError as error:
            await self._rollback_after_failure()
            raise translate_integrity_error(error) from error
        except SQLAlchemyError as error:
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error
        return deleted_camera

    async def _lock_aggregate(
        self,
        camera_id: CameraId,
    ) -> tuple[CameraRow, tuple[CameraSourceRow, ...]]:
        """锁住 Camera 和全部 Source；Camera 不存在时按 ``save`` 契约抛错。"""

        camera_row, source_rows = await self._lock_aggregate_or_none(camera_id)
        if camera_row is None:
            raise CameraNotFoundError(camera_id)
        return camera_row, source_rows

    async def _lock_aggregate_or_none(
        self,
        camera_id: CameraId,
    ) -> tuple[CameraRow | None, tuple[CameraSourceRow, ...]]:
        """按 Camera → Source 顺序取得行锁，Camera 不存在时返回空结果。

        先锁 Camera 可以让针对同一 Camera 的保存和删除互相等待。随后按 Source ID 固定顺序
        锁住全部 Source，避免两个事务以不同顺序持有多条 Source 锁而形成死锁。
        """

        camera_statement = (
            select(CameraRow).where(CameraRow.camera_id == camera_id).with_for_update()
        )
        camera_row = (await self._session.scalars(camera_statement)).one_or_none()
        if camera_row is None:
            return None, ()
        source_statement = (
            select(CameraSourceRow)
            .where(CameraSourceRow.camera_id == camera_id)
            .order_by(CameraSourceRow.source_id.asc())
            .with_for_update()
        )
        source_rows = tuple((await self._session.scalars(source_statement)).all())
        return camera_row, source_rows

    async def _read_sources_in_domain_order(
        self,
        camera_ids: Sequence[CameraId],
    ) -> tuple[CameraSourceRow, ...]:
        """批量读取指定 Camera 的 Source，并按 Camera 配置中的显示顺序排列。

        先按 ``camera_id`` 分组，再按 ``sort_order`` 排序，使列表查询可以直接把连续记录分配
        给对应 Camera，也让 ``rows_to_camera`` 按数据库真实顺序检查数据是否完整。
        """

        statement = (
            select(CameraSourceRow)
            .where(CameraSourceRow.camera_id.in_(camera_ids))
            .order_by(CameraSourceRow.camera_id.asc(), CameraSourceRow.sort_order.asc())
        )
        return tuple((await self._session.scalars(statement)).all())

    async def _get_owned_source_for_update(
        self,
        camera_id: CameraId,
        source_id: SourceId,
    ) -> CameraSourceRow | None:
        """锁定并返回确实属于指定 Camera 的 Source，否则返回 ``None``。

        查询同时包含 ``camera_id`` 和 ``source_id``，不能只按全局 Source ID 查出记录后就在
        Python 中判断归属，否则并发事务可能在检查与后续写入之间改变相关数据。
        """

        statement = (
            select(CameraSourceRow)
            .where(
                CameraSourceRow.camera_id == camera_id,
                CameraSourceRow.source_id == source_id,
            )
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def _rollback_after_failure(self) -> None:
        """数据库操作失败后回滚，使同一个 Session 可以安全地继续使用。

        SQLAlchemy 在 ``flush`` 或查询失败后可能把 Session 标记为失败状态；如果不先回滚，
        后续任何数据库操作都会再次失败。这里的回滚只出现在异常路径，正常业务是否提交仍
        完全由 Unit of Work 决定。
        """

        try:
            await self._session.rollback()
        except SQLAlchemyError as rollback_error:
            raise CameraPersistenceOperationError from rollback_error


def _camera_search_expression(criteria: CameraListCriteria) -> ColumnElement[bool]:
    """生成名称/IP 的不区分大小写包含搜索条件。

    SQL ``LIKE`` 会把 ``%`` 和 ``_`` 当作通配符，反斜杠又是转义字符。产品要求这三个字符
    按用户输入的普通字符搜索，因此先逐一转义，再在两端加 ``%`` 表示“内容中包含”。
    SQLAlchemy 会把最终文本作为绑定参数发送，不会把用户输入拼成 SQL 语句。
    """

    if criteria.q is None:
        # 使用 SQLAlchemy 的 SQL 真值表达式，而不是 Python bool；这样既能让 list 与 count
        # 共用辅助函数，也能保持返回类型始终满足 ``where`` 的 SQL 表达式契约。
        return true()
    escaped = criteria.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return or_(
        CameraRow.name.ilike(pattern, escape="\\"),
        func.host(CameraRow.ip_address).ilike(pattern, escape="\\"),
    )
