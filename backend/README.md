# SOP Vision Backend

Backend 是平台的 FastAPI 控制面。当前已完成公共 HTTP/数据库基础、Camera 领域与持久化层、
MediaMTX v1.20.1 Adapter，以及 PostgreSQL 到 MediaMTX 的后台媒体对账；Camera 业务 handler、
Redis 和 Detector 控制尚未实现。

## 当前能力

| 能力                         | 状态   | 入口                                          |
| ---------------------------- | ------ | --------------------------------------------- |
| 存活检查                     | 可用   | `GET /api/v1/health/live`                     |
| PostgreSQL 就绪检查          | 可用   | `GET /api/v1/health/ready`                    |
| MediaMTX 协议与 Adapter      | 可用   | `contracts/mediamtx-openapi.json`、`ports.py` |
| Camera 领域与持久化          | 可用   | `app/modules/cameras/domain`、`persistence`   |
| 媒体后台对账                 | 可用   | `application/reconciliation.py`               |
| Cameras HTTP 契约            | 已冻结 | 七个路由和 Schema 已进入 OpenAPI              |
| Cameras HTTP 行为            | 未实现 | 七个 handler 当前仅抛出 `NotImplementedError` |
| Redis / WebSocket / Detector | 未实现 | Compose 变量和目标设计不等于应用接入          |

`/api/v1/health/ready` 当前只检查 PostgreSQL，不检查 MediaMTX 或 Redis。MediaMTX 不可用不会令
配置 API 被部署层摘除；媒体故障由状态投影和脱敏对账日志独立表达。

## 环境要求

- Python 3.12
- uv
- PostgreSQL 17（迁移和持久化集成测试）
- MediaMTX v1.20.1（真实协议门禁）

在仓库根目录使用 Compose 启动依赖：

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.dev.yaml \
  up -d --wait postgres redis mediamtx
```

## 本地开发

在 `backend/` 目录执行：

```bash
uv sync --locked
cp .env.local.example .env.local
uv run --env-file .env.local alembic upgrade head
uv run --env-file .env.local python -m app.server \
  --host 127.0.0.1 --port 3001 --reload
```

启动后访问：

- OpenAPI UI：<http://127.0.0.1:3001/docs>
- OpenAPI JSON：<http://127.0.0.1:3001/openapi.json>
- 存活检查：<http://127.0.0.1:3001/api/v1/health/live>
- 就绪检查：<http://127.0.0.1:3001/api/v1/health/ready>

## 配置

应用通过 Pydantic Settings 读取以下变量：

| 环境变量                                   | 默认值                  | 说明                                               |
| ------------------------------------------ | ----------------------- | -------------------------------------------------- |
| `DATABASE_URL`                             | 必填                    | 必须使用 `postgresql+psycopg://` 的 SQLAlchemy URL |
| `DATABASE_POOL_SIZE`                       | `5`                     | 常驻连接池大小                                     |
| `DATABASE_MAX_OVERFLOW`                    | `5`                     | 临时溢出连接数                                     |
| `DATABASE_POOL_TIMEOUT`                    | `30`                    | 获取连接最长等待秒数                               |
| `DATABASE_POOL_RECYCLE`                    | `1800`                  | 连接回收秒数；`-1` 表示禁用按时回收                |
| `DATABASE_CONNECT_TIMEOUT`                 | `10`                    | 建立 PostgreSQL 连接超时秒数                       |
| `DATABASE_ECHO`                            | `false`                 | 是否输出 SQL；参数始终隐藏                         |
| `BACKEND_LOG_LEVEL`                        | `info`                  | 应用与 Uvicorn 日志级别                            |
| `BACKEND_LOG_FORMAT`                       | `console`               | 日志格式：`console` 或单行 `json`                  |
| `TZ`                                       | `Asia/Shanghai`         | 日志显示地区，使用 IANA 时区名称                   |
| `MEDIAMTX_API_URL`                         | `http://mediamtx:9997`  | MediaMTX Control API 地址                          |
| `MEDIAMTX_API_TIMEOUT`                     | `5`                     | Control API 请求超时秒数                           |
| `PUBLIC_WEBRTC_BASE_URL`                   | `http://localhost:8889` | WHEP 公网基础地址；当前播放 handler 尚未使用       |
| `MEDIA_RECONCILIATION_INTERVAL_SECONDS`    | `30`                    | 对账成功或锁竞争后的轮询间隔秒数                   |
| `MEDIA_RECONCILIATION_MAX_BACKOFF_SECONDS` | `300`                   | 连续失败时指数退避的上限秒数                       |
| `BACKEND_CORS_ORIGINS`                     | `http://localhost:8000` | 允许的 Origin，多个值使用逗号分隔                  |

`BACKEND_LOG_LEVEL` 支持 `debug`、`info`、`warning`、`error` 和 `critical`。只在新变量未设置时，
应用才会兼容读取旧 `UVICORN_LOG_LEVEL`；新部署不应继续使用旧变量。`BACKEND_PORT` 只控制
Compose 发布到宿主机的端口，容器内仍监听 `3001`；本地直接启动如需改端口使用 `--port`。
`REDIS_URL` 已在运行环境中预留，但当前代码不会读取它。

console 与 JSON 的 `timestamp` 都按 Backend 进程的 `TZ` 输出 `YYYY-MM-DD HH:mm:ss`，不包含
毫秒、时区偏移或缩写。默认镜像和 Compose 使用 `Asia/Shanghai`；修改地区时应填写系统支持的
IANA 名称，例如 `UTC`。该变量只改变进程本地时间展示，数据库、API 和媒体快照继续使用 UTC。

`DATABASE_URL` 以 Secret 保存，配置校验、日志和 SQL 输出不得回显密码。`TEST_DATABASE_URL`
只供集成测试使用，绝不回退到应用数据库。

## 数据库与事务

Alembic 当前包含运行时基线和 Camera 关系模型。容器启动不会自动迁移数据库：

```bash
uv run --env-file .env.local alembic current
uv run --env-file .env.local alembic upgrade head
```

`cameras` 与 `camera_sources` 有意不建立外键。Camera Repository 通过聚合锁、同事务校验、
显式 Source 清理和完整性巡检维护跨表约束；数据库继续负责主键、IPv4、端口、顺序和同 Camera
唯一性。设计原因和完整规则见 [Cameras 基础能力](../docs/modules/cameras/foundation.md)。

迁移和 Repository 集成测试只接受独立、尚不存在且名称以 `_test` 结尾的数据库。测试会创建并
删除该数据库，拒绝接管预先存在的同名库：

```bash
uv run --env-file .env.local pytest \
  tests/core/database/test_migrations.py \
  tests/modules/cameras/test_repository.py
```

## OpenAPI 跨端契约

`contracts/openapi.json` 从真实应用路由树确定性生成：

```bash
uv run python scripts/export_openapi.py
```

导出不进入 lifespan，也不会连接 PostgreSQL 或 MediaMTX。生成文件不得手工修改；从仓库根目录
运行 `bash scripts/check-cameras-contracts.sh` 可同时重建 OpenAPI 和前端 TypeScript 类型并
检查漂移。Cameras 路径存在于契约中只表示目标接口形状已经冻结。

## 模块边界

```text
backend/
├── migrations/                 # Alembic revision 链
├── scripts/                    # OpenAPI 导出与占位生命周期门禁
├── src/app/
│   ├── factory.py              # 应用、中间件、路由和 lifespan 组装
│   ├── api/
│   │   └── health.py           # 应用存活与 PostgreSQL 就绪探针
│   ├── core/
│   │   ├── database/           # Engine、Session 和 Runtime
│   │   └── http/               # Trace、Problem、校验与 OpenAPI 公共机制
│   └── modules/
│       ├── cameras/
│       │   ├── api/            # Schema、依赖、错误映射和占位 Router
│       │   ├── application/    # 应用端口、媒体 Desired State 与后台对账
│       │   ├── domain/         # 框架无关的 Camera 聚合和值对象
│       │   └── persistence/    # Repository/UoW、Mapper、巡检和对账锁/读取
│       └── stream_gateway/     # MediaMTX Port、URL 规则、状态投影与 Adapter
└── tests/                      # 结构与源码层级对应的测试
```

`api` 拥有不属于具体业务模块的应用级 HTTP 入口；`core` 提供公共基础设施，不依赖业务模块；
`cameras` 拥有 Camera 配置；`stream_gateway` 只拥有媒体运行时适配。
不要建立平行 Backend、Generic Repository 或跨领域的全能 Service。

应用 lifespan 在数据库 Runtime 和 MediaMTX Client 创建后启动媒体对账，不等待首轮完成。关闭时
先取消并等待对账任务，再关闭 Client 和连接池。对账故障不改变 `/health/ready`：该探针仍只检查
PostgreSQL，避免 MediaMTX 故障同时让配置控制面被摘除。详细规则见
[媒体对账](../docs/modules/cameras/media-reconciliation.md)。

## 质量检查

```bash
uv run --env-file .env.local pytest
uv run --env-file .env.local pytest --cov=app --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_mediamtx_contract.py
uv run python scripts/check_camera_placeholders.py foundation
```

未配置 `TEST_DATABASE_URL` 时，数据库集成测试会明确跳过。MVP 发布门禁使用
`uv run python scripts/check_camera_placeholders.py mvp`，它在任一 Cameras handler 仍为占位时失败。

添加依赖使用 `uv add package-name` 或 `uv add --dev package-name`，并同时提交
`pyproject.toml` 与 `uv.lock`。
