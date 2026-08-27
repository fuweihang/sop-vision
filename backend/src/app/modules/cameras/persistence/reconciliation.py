"""PostgreSQL 媒体对账 Reader 与 session advisory lock 实现。"""

from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.modules.cameras.application.ports import CameraMediaStateReader
from app.modules.cameras.domain import Camera, CameraId
from app.modules.cameras.persistence.mapper import rows_to_camera
from app.modules.cameras.persistence.models import CameraRow, CameraSourceRow

# 十六进制 0x534f50564953494f 对应 ASCII ``SOPVISIO``。固定常量在所有 worker/实例间一致，
# 同时避免 Python hash() 的进程随机种子让不同实例拿到不同锁。
MEDIA_RECONCILIATION_LOCK_KEY = 6_003_105_159_835_765_071


class PostgreSQLCameraMediaStateReader:
    """复用持锁 Connection，以单条 LEFT JOIN 重建全部 Camera 聚合。"""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def read_all(self) -> tuple[Camera, ...]:
        """在短只读事务内读取完整快照，ORM Row 不越过本方法。

        ``AsyncSession`` 只用于让现有 ORM Mapper 收到类型化 Row；它绑定 Lease 已持有的同一
        Connection，不会向连接池申请第二条连接。Session 关闭会结束本次只读事务，之后的
        MediaMTX HTTP 写入期间只保留 session lock，不保留数据库事务。
        """

        session = AsyncSession(
            bind=self._connection,
            autoflush=False,
            expire_on_commit=False,
        )
        try:
            # PostgreSQL 必须在本事务第一次数据查询前设置只读模式。即使未来误加入写语句，
            # 数据库也会拒绝，而不是让恢复任务修改 Camera 配置。
            await session.execute(text("SET TRANSACTION READ ONLY"))
            statement = (
                select(CameraRow, CameraSourceRow)
                .select_from(CameraRow)
                .outerjoin(CameraSourceRow, CameraSourceRow.camera_id == CameraRow.camera_id)
                .order_by(
                    CameraRow.camera_id.asc(),
                    CameraSourceRow.sort_order.asc().nulls_last(),
                    CameraSourceRow.source_id.asc().nulls_last(),
                )
            )
            rows = tuple((await session.execute(statement)).all())

            camera_rows: dict[CameraId, CameraRow] = {}
            source_rows_by_camera: defaultdict[CameraId, list[CameraSourceRow]] = defaultdict(list)
            for camera_row, source_row in rows:
                # Python dict 保留插入顺序；配合查询的 ORDER BY，最终 Camera 元组和每台 Camera
                # 的 Source 列表都具有确定顺序，Mapper 无需在内存中再次排序。
                camera_rows[camera_row.camera_id] = camera_row
                if source_row is not None:
                    source_rows_by_camera[camera_row.camera_id].append(source_row)

            # LEFT JOIN 会保留没有 Source 的 Camera；rows_to_camera 必须将其识别为损坏，而不是
            # 静默忽略。Mapper 在 Session 有效期内读取 ORM 字段，返回后只有领域对象离开边界。
            cameras = tuple(
                rows_to_camera(camera_row, source_rows_by_camera[camera_id])
                for camera_id, camera_row in camera_rows.items()
            )
        finally:
            # 只读事务无需 commit；rollback 能明确结束快照且不改变任何数据。
            await session.close()
        return cameras


class PostgreSQLMediaReconciliationLease:
    """用专用 Connection 的 session advisory lock 排除其他对账实例。"""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        lock_key: int = MEDIA_RECONCILIATION_LOCK_KEY,
    ) -> None:
        self._engine = engine
        self._lock_key = lock_key

    @asynccontextmanager
    async def acquire(
        self,
    ) -> AsyncGenerator[CameraMediaStateReader | None]:
        """非阻塞尝试获取锁，并保证正常、异常和取消路径都释放连接与锁。"""

        connection = await self._engine.connect()
        locked = False
        try:
            # advisory lock 是 PostgreSQL session 级资源，必须从获取到释放始终使用这条物理
            # Connection；中途归还连接池会让锁跟着连接留给无关请求，并失去互斥保证。
            locked = (
                await connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": self._lock_key},
                )
            ) is True
            # SQLAlchemy 执行 SELECT 时会自动开启事务；session lock 不依赖该事务，所以立刻
            # 提交，避免远端 HTTP 调用期间持有无意义的数据库事务。
            await connection.commit()
            if not locked:
                yield None
                return
            yield PostgreSQLCameraMediaStateReader(connection)
        finally:
            # Reader 或调用方异常时可能仍有隐式事务，必须先结束它，unlock 才不会把失败事务
            # 状态带回连接池。
            if connection.in_transaction():
                await connection.rollback()
            if locked:
                await self._unlock_or_invalidate(connection)
            await connection.close()

    async def _unlock_or_invalidate(self, connection: AsyncConnection) -> None:
        """释放锁；无法证明已释放时丢弃物理连接，禁止带锁连接回池。"""

        try:
            unlocked = (
                await connection.scalar(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": self._lock_key},
                )
            ) is True
            await connection.commit()
        except BaseException:
            # invalidate 会让池关闭底层 DBAPI 连接；PostgreSQL 在 session 结束时自动释放锁。
            await connection.invalidate()
            raise
        if not unlocked:
            # pg_advisory_unlock 返回 false 表示当前 session 没持有目标锁。此时本地 locked 状态
            # 与数据库已经不一致，继续复用该连接无法证明安全，所以同样将其移出连接池。
            await connection.invalidate()
