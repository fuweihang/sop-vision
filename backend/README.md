# Backend

Backend 是 SOP Vision 的统一 FastAPI 服务。业务能力按模块组织；当前包含
`stream_gateway` 模块，负责提供视频流管理 API，并通过 Docker Compose 内部网络调用
MediaMTX Control API。

## 当前能力

- FastAPI 应用工厂与 lifespan 资源管理。
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
uv run --env-file ../.env uvicorn app.main:app \
  --app-dir src \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

若根目录没有 `.env`，可先执行：

```bash
cp ../.env.example ../.env
```

启动后可访问：

- OpenAPI：<http://localhost:8000/docs>
- 存活检查：<http://localhost:8000/api/v1/health/live>
- 就绪检查：<http://localhost:8000/api/v1/health/ready>

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
| `MEDIAMTX_API_URL` | `http://mediamtx:9997` | MediaMTX Control API 内部地址 |
| `MEDIAMTX_API_TIMEOUT` | `5` | Control API 请求超时（秒） |
| `DATABASE_URL` | `postgresql://...@postgres:5432/sop_vision` | PostgreSQL 内部连接地址（持久化代码待实现） |
| `PUBLIC_WEBRTC_BASE_URL` | `http://localhost:8889` | 返回给浏览器的 WebRTC 公共地址 |
| `BACKEND_PORT` | `8000` | Backend 映射到宿主机的端口 |
| `BACKEND_LOG_LEVEL` | `info` | Uvicorn 日志级别 |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173` | 允许的前端 Origin，多个值用逗号分隔 |

应用尚未读写摄像头数据库。MediaMTX 当前 path 配置仍作为首期运行时状态来源。

## 项目结构

```text
backend/
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── src/
│   └── app/
│       ├── main.py
│       ├── core/
│       │   └── config.py
│       └── modules/
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
uv run pytest
uv run pytest --cov=app --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
```

添加依赖时使用 `uv add package-name` 或 `uv add --dev package-name`，并同时提交
`pyproject.toml` 与 `uv.lock`。
