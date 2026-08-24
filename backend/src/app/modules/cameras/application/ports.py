"""Camera 应用服务需要的数据库操作接口。

这里只描述“应用服务能够做什么”，不指定 SQLAlchemy、PostgreSQL 或内存 Fake 如何实现。
生产代码和测试代码遵守同一组方法，应用服务因此不需要为两种实现编写不同逻辑。
"""

from dataclasses import dataclass
from typing import Protocol

from app.modules.cameras.domain import Camera, CameraId

# 搜索文本和单页数量在所有 Repository 实现中使用同一上限，避免真实数据库与测试 Fake
# 对相同输入给出不同结果。API 层后续也会复用这两个业务边界。
CAMERA_LIST_QUERY_MAX_LENGTH = 100
CAMERA_LIST_PAGE_SIZE_MAX = 100


@dataclass(frozen=True, slots=True)
class CameraListCriteria:
    """已经去掉首尾空白的 Camera 搜索条件。

    后续 API 层负责去掉 HTTP 查询参数的首尾空白，并把只包含空白的输入变成 ``None``。
    本类仍会再次检查，因为定时任务、脚本或单元测试也可以直接调用 Repository，不能假定
    所有调用都来自 HTTP。
    """

    q: str | None = None

    def __post_init__(self) -> None:
        """拒绝未清理或过长的查询文本，保证所有 Repository 收到相同格式。"""

        if self.q is None:
            return
        if not isinstance(self.q, str):
            raise TypeError("Camera 列表搜索条件必须是字符串或 None。")
        if not self.q or self.q != self.q.strip():
            raise ValueError("Camera 列表搜索条件必须是规范化后的非空字符串。")
        if len(self.q) > CAMERA_LIST_QUERY_MAX_LENGTH:
            raise ValueError(f"Camera 列表搜索条件不能超过 {CAMERA_LIST_QUERY_MAX_LENGTH} 个字符。")


class CameraRepository(Protocol):
    """以“一个 Camera 和它的全部 Source”为单位读写数据。

    接口故意不提供单独新增、更新或删除一条 Source 的方法。所有 Source 必须随 Camera 一起
    保存，这样默认 Source、Source 顺序和“至少一路 Source”等规则不会被局部写入绕过。
    Repository 可以把改动发送到 Session，但不能自行提交事务。
    """

    async def add(self, camera: Camera) -> None:
        """登记一个尚未存在的新 Camera 及其全部 Source。

        Camera ID 或任一 Source ID 已存在时必须失败，不能把新增操作悄悄改成更新。
        """

        ...

    async def save(self, camera: Camera) -> None:
        """用传入的完整配置覆盖一个已经存在的 Camera。

        实现需要同时处理保留、新增、删除和重排 Source。目标 Camera 不存在时抛出
        ``CameraNotFoundError``，不能在更新路径创建新 Camera。
        """

        ...

    async def get(self, camera_id: CameraId, for_update: bool = False) -> Camera | None:
        """读取一个 Camera 及其全部 Source，找不到时返回 ``None``。

        ``for_update=True`` 只供准备修改同一 Camera 的业务使用，它会让并发写入按顺序等待；
        普通详情和列表读取不应开启这个选项。
        """

        ...

    async def list(
        self,
        criteria: CameraListCriteria,
        page: int,
        page_size: int,
    ) -> tuple[Camera, ...]:
        """按搜索条件返回一页完整 Camera。

        排序固定为创建时间升序，再按 Camera ID 升序；固定的第二排序字段可以避免多条记录
        创建时间相同时在不同页面之间来回移动。页码超出结果范围时返回空元组。
        """

        ...

    async def count(self, criteria: CameraListCriteria) -> int:
        """返回符合搜索条件的 Camera 总数，供 API 计算分页信息。"""

        ...

    async def delete(self, camera_id: CameraId) -> Camera | None:
        """删除 Camera 及其全部 Source，并返回删除前的完整数据。

        返回旧数据是为了让后续应用服务在数据库提交成功后，知道需要清理哪些 MediaMTX
        资源。目标已经不存在时返回 ``None``，重复删除不会制造新的数据库错误。
        """

        ...


class CameraUnitOfWork(Protocol):
    """控制一次 Camera 业务操作中的提交和回滚。

    同一个 Unit of Work 里的 ``cameras`` Repository 必须使用同一个数据库 Session。它只供
    一个业务操作顺序使用，不能在多个请求或并发 asyncio 任务之间共享。
    """

    @property
    def cameras(self) -> CameraRepository:
        """返回当前事务使用的 Repository；调用方不能替换 UoW 内部的事务资源。"""

        ...

    async def commit(self) -> None:
        """把本次业务操作产生的全部数据库修改一起提交。"""

        ...

    async def rollback(self) -> None:
        """丢弃本次业务操作尚未提交的全部数据库修改。"""

        ...


def validate_camera_list_pagination(page: int, page_size: int) -> int:
    """检查页码和每页数量，并返回 SQL 查询需要跳过的记录数。

    Python 中 ``bool`` 是 ``int`` 的子类，因此必须显式拒绝 ``True`` 和 ``False``，否则它们
    会被误当成页码 1 和 0。限制 ``page_size`` 也能防止非 HTTP 调用方一次加载过多 Camera
    及其全部 Source。
    """

    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("Camera 列表页码必须是大于等于 1 的整数。")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= CAMERA_LIST_PAGE_SIZE_MAX
    ):
        raise ValueError(f"Camera 列表每页数量必须在 1-{CAMERA_LIST_PAGE_SIZE_MAX} 之间。")
    return (page - 1) * page_size
