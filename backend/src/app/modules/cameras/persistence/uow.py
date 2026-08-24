"""统一提交或回滚一次 Camera 业务操作使用的数据库事务。"""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cameras.application.errors import CameraPersistenceOperationError
from app.modules.cameras.persistence.constraints import translate_integrity_error
from app.modules.cameras.persistence.repository import SQLAlchemyCameraRepository


class SQLAlchemyCameraUnitOfWork:
    """让 Camera Repository 和事务操作使用调用方提供的同一个 Session。

    FastAPI 依赖负责创建并关闭请求级 Session，本类只负责暴露 Repository 以及明确的
    ``commit``/``rollback``。它不会在退出作用域时自动提交，应用服务必须在业务规则全部
    成功后主动调用 ``commit``。
    """

    def __init__(self, session: AsyncSession) -> None:
        """保存请求级 Session，并把同一个对象交给 Camera Repository。"""

        self._session = session
        self.cameras = SQLAlchemyCameraRepository(session)

    async def commit(self) -> None:
        """提交本次业务操作，并把数据库异常转换为应用错误。

        数据库中的 Source 后缀和顺序会在事务提交时做最终重复检查，所以冲突可能直到
        ``commit`` 才出现。这里和 Repository 的 ``flush`` 使用相同的错误转换。提交一旦
        失败，SQLAlchemy Session 不能继续使用；必须先回滚恢复 Session，再把不包含 SQL、
        密码或连接信息的 Camera 错误抛给应用服务。
        """

        try:
            await self._session.commit()
        except IntegrityError as error:
            # 数据内容违反数据库规则，例如同一 Camera 出现重复 Source 后缀。
            await self._rollback_after_failure()
            raise translate_integrity_error(error) from error
        except SQLAlchemyError as error:
            # 连接失败等其他 SQLAlchemy 错误统一隐藏底层 SQL 和连接信息。
            await self._rollback_after_failure()
            raise CameraPersistenceOperationError from error
        except BaseException:
            # asyncio 任务取消不属于业务错误，但仍要回滚，防止连接带着未完成事务返回连接池。
            await self._session.rollback()
            raise

    async def rollback(self) -> None:
        """丢弃当前事务内尚未提交的全部修改。

        应用服务在业务校验失败或后续步骤无法继续时可以显式调用。若回滚本身也遇到数据库
        错误，只向上抛通用 Camera 错误，避免数据库连接信息进入应用层。
        """

        try:
            await self._session.rollback()
        except SQLAlchemyError as error:
            raise CameraPersistenceOperationError from error

    async def _rollback_after_failure(self) -> None:
        """在提交失败后恢复 Session；此辅助方法只供异常路径使用。"""

        try:
            await self._session.rollback()
        except SQLAlchemyError as error:
            raise CameraPersistenceOperationError from error
