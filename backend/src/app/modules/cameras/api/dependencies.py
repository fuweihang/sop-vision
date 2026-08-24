"""把 FastAPI 提供的请求级数据库 Session 组装成 Camera Unit of Work。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_database_session
from app.modules.cameras.application.ports import CameraUnitOfWork
from app.modules.cameras.persistence.uow import SQLAlchemyCameraUnitOfWork


def get_camera_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CameraUnitOfWork:
    """返回只服务于当前请求的 Camera Unit of Work。

    ``get_database_session`` 保证每个请求拿到独立的 ``AsyncSession``，并在请求结束时关闭它。
    这里不再创建第二个 Session，也不负责提交、回滚或关闭；这些职责分别属于应用服务、
    Unit of Work 和数据库 Session 依赖。Repository 与 Unit of Work 因此会使用同一个事务。
    """

    # 保持这个函数只做对象组装，便于 FastAPI 测试通过 dependency_overrides 替换整个 UoW。
    return SQLAlchemyCameraUnitOfWork(session)
