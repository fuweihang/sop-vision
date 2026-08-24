# Backend

Backend 是 SOP Vision 的统一 FastAPI 服务。业务能力按模块组织；当前包含
`stream_gateway` 模块，负责提供视频流管理 API，并通过 Docker Compose 内部网络调用
MediaMTX Control API。

## 当前能力

- FastAPI 应用工厂与 lifespan 资源管理。
- SQLAlchemy async Engine/Session factory 与 Alembic 迁移骨架。
- 无外键 `cameras`/`camera_sources` 关系模型、事务 Repository 与完整性巡检。
- `/api/v1/health/live` 存活检查。
- `/api/v1/health/ready` MediaMTX Control API 就绪检查。
- 摄像头请求/响应模型和路由骨架。
- 共享异步 MediaMTX 客户端。
- uv、Ruff、pytest 和 Docker 构建配置。

摄像头 CRUD 尚未实现。后续实现位于
`app/modules/stream_gateway/api/cameras.py` 和
`app/modules/stream_gateway/services/mediamtx.py`。

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- 可选：Docker 与 Docker Compose

## 本地开发

在 `backend/` 目录执行：

```bash
uv sync
cp .env.local.example .env.local
uv run --env-file .env.local uvicorn app.main:app \
  --app-dir src \
  --host 127.0.0.1 \
  --port 3001 \
  --reload
```

启动后可访问：

- OpenAPI：<http://localhost:3001/docs>
- 存活检查：<http://localhost:3001/api/v1/health/live>
- 就绪检查：<http://localhost:3001/api/v1/health/ready>

`ready` 会访问 `${MEDIAMTX_API_URL}/v3/config/paths/list`。MediaMTX 未启动或
Control API 未启用时返回 HTTP 503。

## Docker Compose

在仓库根目录执行：

```bash
cp .env.example .env
docker compose up --build --wait
docker compose logs -f backend
```

Backend 在 Compose 网络中通过 `http://mediamtx:9997` 访问 MediaMTX，并通过
`DATABASE_URL` 获取 PostgreSQL 连接地址。Control API 端口不会映射到宿主机。

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 必填 | SQLAlchemy PostgreSQL URL，必须显式使用 `postgresql+psycopg://` |
| `DATABASE_POOL_SIZE` | `5` | 常驻连接池大小 |
| `DATABASE_MAX_OVERFLOW` | `5` | 连接池允许的临时溢出连接数 |
| `DATABASE_POOL_TIMEOUT` | `30` | 获取连接的最长等待秒数 |
| `DATABASE_POOL_RECYCLE` | `1800` | 连接回收秒数；`-1` 表示不按时间回收 |
| `DATABASE_CONNECT_TIMEOUT` | `10` | 建立 PostgreSQL 连接的超时秒数 |
| `DATABASE_ECHO` | `false` | 是否输出 SQL；即使开启也隐藏 SQL 参数 |
| `MEDIAMTX_API_URL` | `http://mediamtx:9997` | MediaMTX Control API 内部地址 |
| `MEDIAMTX_API_TIMEOUT` | `5` | Control API 请求超时（秒） |
| `PUBLIC_WEBRTC_BASE_URL` | `http://localhost:8889` | 返回给浏览器的 WebRTC 公共地址 |
| `BACKEND_PORT` | `3001` | Backend 映射到宿主机的端口 |
| `BACKEND_LOG_LEVEL` | `info` | Uvicorn 日志级别 |
| `BACKEND_CORS_ORIGINS` | `http://localhost:8000` | 允许的前端 Origin，多个值用逗号分隔 |

Camera 持久化底层已经可用，但业务 CRUD 路由尚未接入。跨表引用由 Repository 通过
Camera 行锁、同事务校验和显式 Source 清理维护；数据库不会用外键兜底。MediaMTX 当前
path 配置仍作为首期运行时状态来源。

`DATABASE_URL` 的密码在 Settings 表示和校验异常文本中脱敏。`TEST_DATABASE_URL`
不是应用配置，只供数据库集成测试使用；测试绝不回退到应用数据库。

## 数据库迁移

在 `backend/` 目录执行正常的前向迁移：

```bash
uv run --env-file .env.local alembic current
uv run --env-file .env.local alembic upgrade head
```

完整回滚链只能在独立测试数据库上验收。`.env.local` 中的
`TEST_DATABASE_URL` 必须指向与应用库不同、名称以 `_test` 结尾且尚不存在的数据库：

```bash
uv run --env-file .env.local pytest \
  tests/core/database/test_migrations.py \
  tests/modules/cameras/test_repository.py \
  -q
```

测试会创建独立数据库，执行迁移升级、回滚、约束、引用巡检和并发锁验收，并在结束时
删除本次创建的数据库。它拒绝接管或删除预先存在的同名数据库。

## 项目结构

```text
backend/
├── alembic.ini
├── Dockerfile
├── migrations/
│   ├── env.py
│   └── versions/
├── pyproject.toml
├── uv.lock
├── src/
│   └── app/
│       ├── main.py
│       ├── core/
│       │   ├── config.py
│       │   └── database/
│       └── modules/
│           ├── cameras/
│           │   └── persistence/
│           └── stream_gateway/
│               ├── api/
│               ├── schemas/
│               └── services/
└── tests/
    ├── conftest.py
    ├── test_config.py
    └── modules/
        └── stream_gateway/
            └── test_health.py
```

`app.main` 只负责应用组装和共享生命周期；`stream_gateway` 模块封装自己的路由、
数据模型、依赖和 MediaMTX 适配器。后续后端能力应继续放在 `app/modules/` 下，避免再建立
独立的后端工程。

## 质量检查

```bash
uv run --env-file .env.local pytest
uv run --env-file .env.local pytest --cov=app --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
```

未配置 `TEST_DATABASE_URL` 时，迁移集成测试会明确跳过；CI 和数据库迁移验收必须配置
该变量并确认测试实际执行。

添加依赖时使用 `uv add package-name` 或 `uv add --dev package-name`，并同时提交
`pyproject.toml` 与 `uv.lock`。
