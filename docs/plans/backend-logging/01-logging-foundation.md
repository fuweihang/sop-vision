# 01｜统一日志基础与 Backend 启动入口

## 任务目标

建立所有运行时 Logger 共用的配置、Formatter、字段过滤和级别控制。完成后，即使业务调用仍保留
旧消息，输出也必须具有统一时间、级别和组件列，`BACKEND_LOG_LEVEL` 必须真正控制应用 Logger。

## 当前上下文 / 前置条件

- 总体规则见同目录 `README.md`，实施时必须遵守其中的字段白名单和安全要求。
- 当前应用入口是 `backend/src/app/main.py` 中模块级 `app = create_app()`。
- Docker 直接执行 `uvicorn app.main:app`。
- 测试会导入 `app.main.create_app`；日志初始化不得在普通模块导入时破坏 pytest/caplog Handler。
- `backend/src/app/core/http/trace.py` 已提供 trace ContextVar 和 `TraceIdLogFilter`。
- Uvicorn 锁定版本为 `0.52.1`，programmatic `log_config` 可在主进程和 reload/worker 子进程应用
  同一套标准库 logging 配置。
- 本任务不依赖后续任务。

## 实施范围

新增：

- `backend/src/app/core/logging.py`
- `backend/src/app/server.py`
- `backend/tests/core/test_logging.py`
- `backend/tests/test_server.py`

修改：

- `backend/src/app/core/config.py`
- `backend/src/app/core/http/trace.py`
- `backend/Dockerfile`
- `compose.yaml`
- `.env.example`
- `backend/.env.local.example`
- `backend/README.md`
- `README.md`
- `AGENTS.md`
- `backend/tests/test_config.py`
- `backend/tests/test_main.py`

需要交付：

- `BACKEND_LOG_LEVEL=debug|info|warning|error|critical`，默认 `info`。
- `BACKEND_LOG_FORMAT=console|json`，默认 `console`。
- Backend 容器使用 `TZ=Asia/Shanghai` 作为默认地区；Formatter 根据进程 `TZ` 输出
  `YYYY-MM-DD HH:mm:ss`，console 与 JSON 不显示毫秒或时区后缀。
- `BACKEND_LOG_LEVEL` 优先；仅当它未设置时，兼容读取已有 `UVICORN_LOG_LEVEL`。示例和文档不再
  主动使用旧变量，但本轮不让现有部署静默退回 `info`；旧变量也只接受同一组五个合法值。
- 总览规定的地区时间 console Formatter、JSON Formatter、字段白名单、组件映射、单行转义和安全异常
  堆栈。
- 一个只返回纯字符串 `error_type/error_frames` 的安全异常 helper，供应用捕获未知异常时使用；
  helper 和 Formatter 都不得把异常文本或异常对象写入 LogRecord。
- 自动从现有 ContextVar 读取 trace 的 Handler Filter；没有 trace 时省略字段。
- 总览 Logger 级别表规定的 root、`app.*`、Uvicorn、httpx/httpcore 和 SQLAlchemy 级别。
- 独立 `app.server` 启动入口，先配置日志，再通过字符串 `app.main:app` 启动 Uvicorn。
- `app.server` 的最小 CLI：`--host` 默认 `127.0.0.1`、`--port` 默认 `3001`、`--reload`、
  `--workers` 默认 `1`。`--reload` 与 `--workers > 1` 同时出现时在启动前报错。
- Docker 固定执行 `python -m app.server --host 0.0.0.0 --port 3001`；本地开发执行
  `python -m app.server --host 127.0.0.1 --port 3001 --reload`。
- 既有 `BACKEND_PORT` 继续只控制 Compose 发布到宿主机的端口，容器内仍为 `3001`；本地直接启动
  如需改端口使用 `--port`。本计划不新增 `BACKEND_HOST/BACKEND_RELOAD/BACKEND_WORKERS` 环境变量。

## 明确不做

- 不修改业务日志 message、event 或级别。
- 不实现持续故障抑制。
- 暂时保留 Uvicorn access log，任务 3 再替换。
- 不修改 SQLAlchemy Engine 的 `echo` 参数。
- 不修改 Alembic 日志。
- 不引入 structlog、loguru 或 OpenTelemetry。
- 不实现彩色日志、日志文件轮转或远端采集。

## 实施步骤

1. 先用测试固定总览中的 `TZ` 地区时间、level/组件映射、console 短键与字段顺序、单行转义、空字段
   省略、有效 `0` 保留、未知字段忽略、JSON 数值类型和安全异常输出。
2. 实现日志字段常量、组件映射、安全异常 helper、trace Filter、console/JSON Formatter 和配置
   构造函数。Formatter 只能处理白名单字段，不得修改业务 LogRecord 来制造另一套格式。
3. 统一使用一个无 ANSI 的 `stderr` Handler；配置时保持 `disable_existing_loggers=False`，移除并
   替换本模块自己安装的旧 Handler，但不得删除 pytest/caplog 或宿主进程 Handler。重复配置不得
   增加 Handler 或重复输出。
4. 修改现有 `TraceIdLogFilter`，非 HTTP 上下文写入 `None` 而不是 `-`；增加 Settings 字段、枚举
   合法值、`UVICORN_LOG_LEVEL` 回退优先级和配置测试。
5. 实现 `app.server`：
   - 在服务器启动入口加载 Settings 和日志配置。
   - 保持 `app.main` 可被测试和 OpenAPI 导出安全导入。
   - 使用 `argparse` 提供上述四个启动参数，并在 `main()` / `if __name__ == "__main__"` 内调用
     Uvicorn，避免 reload/worker 子进程重复执行不安全的模块级启动逻辑。
   - 日志模块生成同一个标准库 `dictConfig` 字典：`app.server` 在调用 Uvicorn 前先应用一次，使
     启动阶段已有统一输出；随后把同一字典作为 `log_config` 传给 Uvicorn，使 reload/worker
     子进程也应用它。重复应用必须由步骤 3 的测试证明不会叠加 Handler。
   - 向 Uvicorn 传入字符串应用路径、解析后的 log level 和 `access_log=True`；任务 1 仍启用
     Uvicorn access log。
6. Docker 改用 `app.server`；Compose 直接传 `BACKEND_LOG_LEVEL/BACKEND_LOG_FORMAT/TZ`，不再只设置
   `UVICORN_LOG_LEVEL`。
7. 更新环境变量示例、Backend README、根 README 和 `AGENTS.md`，所有受支持的 Backend
   启动命令都经过 `app.server`。

## 验证方式

```bash
cd backend
uv run pytest tests/core/test_logging.py tests/test_server.py tests/test_config.py tests/test_main.py
uv run ruff check .
uv run ruff format --check .
cd ..
docker compose config
```

人工检查：

- 默认 `info/console` 下，Uvicorn error 和业务告警具有相同时间、级别和组件列。
- `BACKEND_LOG_LEVEL=debug` 时应用 DEBUG 日志可见。
- `BACKEND_LOG_FORMAT=json` 时每行都是可独立解析的 JSON。
- 重复初始化不会让同一条日志出现两次。
- 未知 `extra` 和敏感测试哨兵不会出现在 console 或 JSON。
- 本地参数保留 `127.0.0.1:3001 + reload`，Docker 参数为 `0.0.0.0:3001`；非法
  `--reload --workers 2` 在调用 Uvicorn 前失败。
- 只设置旧 `UVICORN_LOG_LEVEL=debug` 仍能得到应用 DEBUG；同时设置两个变量时以
  `BACKEND_LOG_LEVEL` 为准。

## 完成标准

- 应用与 Uvicorn error 日志使用同一日志配置。
- 日志级别和格式由 Backend 配置控制。
- 测试导入 `app.main` 不会重置 pytest/caplog Handler。
- Formatter 只展开总览中允许的字段。
- Docker 和本地启动文档都使用新入口。
- 根 README 和 `AGENTS.md` 不再提供绕过统一配置的 `uvicorn app.main:app` 命令。
- 本任务的测试、Ruff 和 Compose 配置检查通过。

## 与下一任务的衔接信息

任务 2 必须复用本任务交付的字段白名单、组件映射、Formatter 和自动 trace Filter。交接时记录：

- 实际新增的日志配置 API 和模块路径。
- `LogRecord.extra` 的字段写法和 event 命名约束。
- console/JSON Formatter 测试入口。
- 最终使用的 Backend 启动命令。

任务 2 不得在业务模块中新增 Formatter 或手工拼统一前缀。
