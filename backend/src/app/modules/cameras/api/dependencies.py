"""Camera API 的请求参数与请求级基础设施依赖。"""

from typing import Annotated, Self

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_database_session
from app.modules.cameras.application.ports import (
    CAMERA_LIST_PAGE_SIZE_MAX,
    CAMERA_LIST_QUERY_MAX_LENGTH,
    CameraListCriteria,
    CameraUnitOfWork,
)
from app.modules.cameras.domain import Clock, IdGenerator, SystemClock, Uuid4Generator
from app.modules.cameras.persistence.uow import SQLAlchemyCameraUnitOfWork


class CameraListParameters(BaseModel):
    """已经规范化、可直接传给列表用例的不可变查询参数。

    ``extra="ignore"`` 保持 Foundation 契约：旧 ``sort`` 或其他额外查询参数不进入对象，
    不出现在 OpenAPI，也不会改变 Repository 固定排序。
    """

    model_config = ConfigDict(
        # FastAPI 默认忽略额外查询参数；模型层保持相同策略，防止绕过 HTTP 直接构造时产生
        # 与线上不同的 sort/filter 行为。frozen 则保证参数进入 Query Key 或用例后不再漂移。
        extra="ignore",
        frozen=True,
        # 在长度判断前 trim，使两端带空白但有效内容恰好 100 字符的 q 仍符合契约。
        str_strip_whitespace=True,
    )

    # 分页边界在 HTTP 层尽早给出字段级 422；Repository 仍会二次校验，以保护非 HTTP 调用方。
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=CAMERA_LIST_PAGE_SIZE_MAX)
    q: str | None = Field(default=None, max_length=CAMERA_LIST_QUERY_MAX_LENGTH)

    @model_validator(mode="after")
    def normalize_blank_query(self) -> Self:
        """trim 由模型配置完成；仅空白文本随后收敛成唯一的 ``None`` 表示。"""

        if self.q == "":
            # 返回副本而非修改 self，既遵守 frozen 模型，也让空字符串、纯空白与未提供形成
            # 唯一表示，避免同一列表请求生成多个前端缓存键。
            return self.model_copy(update={"q": None})
        return self

    @property
    def criteria(self) -> CameraListCriteria:
        """构造 Repository 共享的最小搜索值对象，不把分页或排序混入 criteria。"""

        return CameraListCriteria(q=self.q)


# Query 参数先 trim 再限制长度；该约束放在 FastAPI 参数声明上，非法 q 才会进入统一的
# RequestValidationError 处理器，而不是在依赖函数内抛出普通 ValueError 形成 500。
NormalizedCameraQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=CAMERA_LIST_QUERY_MAX_LENGTH),
]


async def get_camera_list_parameters(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=CAMERA_LIST_PAGE_SIZE_MAX)] = 20,
    q: Annotated[NormalizedCameraQuery | None, Query()] = None,
) -> CameraListParameters:
    """从声明式标量查询参数构造值对象，并保留可覆盖的异步依赖入口。

    这里不直接把整个 Pydantic 模型标为 ``Query``：显式声明三个公共参数能确保额外查询参数
    继续按 FastAPI 默认行为忽略，也避免它们意外进入 OpenAPI 或后续 Query Key。使用异步
    依赖还可避免为这段纯构造逻辑切换到线程池。
    """

    # ``q or None`` 把已 trim 的空字符串收敛为 None；模型 validator 继续作为直接构造时的
    # 防线，两条入口因而保持相同语义。
    return CameraListParameters(page=page, page_size=page_size, q=q or None)


# 对路由暴露稳定的依赖别名，后续列表 handler 不必重复 Depends 声明，也不会误把整个参数
# 模型当作请求体。
CameraListParametersDependency = Annotated[
    CameraListParameters,
    Depends(get_camera_list_parameters),
]


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


def get_camera_id_generator() -> IdGenerator:
    """为一次请求提供无状态 UUID v4 生成器，并保留测试覆盖入口。"""

    return Uuid4Generator()


def get_camera_clock() -> Clock:
    """为 Camera 写入和媒体失败投影提供统一 UTC 时钟。"""

    return SystemClock()


# 三个别名让 Router 只声明端口，不接触 SQLAlchemy 或生产实现。测试覆盖原始 provider 函数
# 即可替换整个请求的事务、ID 序列和时间，不需要修改应用级全局状态。
CameraUnitOfWorkDependency = Annotated[
    CameraUnitOfWork,
    Depends(get_camera_unit_of_work),
]
CameraIdGeneratorDependency = Annotated[
    IdGenerator,
    Depends(get_camera_id_generator),
]
CameraClockDependency = Annotated[
    Clock,
    Depends(get_camera_clock),
]
