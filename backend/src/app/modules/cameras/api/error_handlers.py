"""把 Cameras 领域/持久化错误映射到公共 HTTP Problem。"""

from fastapi import FastAPI, Request

from app.core.http import FieldError, add_http_exception_handler, problem_response
from app.modules.cameras.application.errors import (
    CameraAggregateInvalidError,
    CameraConstraintViolationError,
    CameraNotFoundError,
    CameraPersistenceOperationError,
)
from app.modules.cameras.domain import CameraAggregateCorruptedError, CameraValidationError


async def camera_validation_error_handler(request: Request, error: CameraValidationError):
    """把领域校验错误逐项转换为公开的 422 字段 Problem。

    领域错误已经只保存固定 detail、稳定 code 和字段路径，因此可以转换；这里仍然重新构造
    HTTP FieldError，避免 API Schema 直接依赖或序列化领域 dataclass。
    """

    return problem_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        title="请求字段验证失败",
        detail="存在一个或者多个无效字段。",
        errors=tuple(
            FieldError(field=item.field, code=item.code.value, detail=item.detail)
            for item in error.errors
        ),
    )


async def camera_not_found_error_handler(request: Request, error: CameraNotFoundError):
    """把 Camera 不存在转换为稳定 404。

    ID 来自已经通过 Canonical UUID 或领域规则校验的错误字段；不从 URL 字符串或请求体重新
    解析，避免把未经审查的内容放入公开 context。
    """

    return problem_response(
        request,
        status_code=404,
        code="CAMERA_NOT_FOUND",
        title="Camera 不存在",
        detail="未找到指定的 Camera。",
        context={"camera_id": str(error.camera_id)},
    )


async def camera_aggregate_invalid_error_handler(
    request: Request,
    _error: CameraAggregateInvalidError,
):
    """把详情读取发现的损坏聚合转换为稳定且不含损坏项的 500。"""

    return problem_response(
        request,
        status_code=500,
        code="CAMERA_AGGREGATE_INVALID",
        title="Camera 数据无效",
        detail="Camera 配置暂时无法读取。",
    )


async def camera_database_error_handler(
    request: Request,
    _error: CameraPersistenceOperationError,
):
    """把已知数据库操作失败转换为可重试的 503。

    原始异常链可能带 SQL、连接串、约束名和参数，因此响应只使用固定依赖错误语义。该映射
    不承诺事务是否提交；具体用例仍需按自己的幂等与结果确认流程处理重试。
    """

    return problem_response(
        request,
        status_code=503,
        code="DATABASE_UNAVAILABLE",
        title="数据库暂不可用",
        detail="数据库暂时无法完成请求，请稍后重试。",
    )


async def camera_internal_invariant_error_handler(
    request: Request,
    _error: CameraAggregateCorruptedError | CameraConstraintViolationError,
):
    """把服务端聚合/持久化不变量失败转换为安全 500。

    聚合损坏和大多数数据库约束冲突代表服务端缺陷或数据异常，不能伪装成用户 422。只有
    后续应用服务掌握准确数组下标时，才可把重复 Source 后缀显式转换为字段校验错误。
    """

    return problem_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        title="服务器内部错误",
        detail="服务器暂时无法完成请求。",
    )


def install_camera_exception_handlers(application: FastAPI) -> None:
    """注册 Cameras 已存在的领域与依赖错误，不创建任何业务路由。

    安装函数位于 Cameras API 边界，使 ``app.core.http`` 保持业务无关；应用工厂显式调用后，
    测试应用和生产应用会获得一致映射。
    """

    add_http_exception_handler(application, CameraValidationError, camera_validation_error_handler)
    add_http_exception_handler(application, CameraNotFoundError, camera_not_found_error_handler)
    add_http_exception_handler(
        application,
        CameraAggregateInvalidError,
        camera_aggregate_invalid_error_handler,
    )
    # 子类分别注册而不是笼统捕获 CameraPersistenceError：NotFound 是 404，依赖不可用是
    # 503，而服务端约束破坏必须是 500，混为一个 handler 会掩盖不同恢复语义。
    add_http_exception_handler(
        application,
        CameraPersistenceOperationError,
        camera_database_error_handler,
    )
    add_http_exception_handler(
        application,
        CameraAggregateCorruptedError,
        camera_internal_invariant_error_handler,
    )
    add_http_exception_handler(
        application,
        CameraConstraintViolationError,
        camera_internal_invariant_error_handler,
    )
