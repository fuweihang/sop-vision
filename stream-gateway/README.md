# Stream Gateway

Stream Gateway 是 SOP Vision 的 FastAPI 后端服务，负责向前端提供稳定的业务 API，并通过 Docker Compose 内部网络调用 MediaMTX Control API。当前项目骨架已经提供应用配置、路由分层、共享异步 MediaMTX 客户端、健康检查和测试基础设施。

## 当前状态

已经实现：

- uv 项目和锁文件管理。
- FastAPI 应用工厂与 lifespan 资源管理。
- Uvicorn 开发和容器启动入口。
- `/api/v1/health/live` 存活检查。
- `/api/v1/health/ready` MediaMTX Control API 就绪检查。
- 摄像头请求/响应模型和路由模块骨架。
- Ruff、pytest 和 Docker 构建配置。

尚未实现摄像头 CRUD。后续将在 `app/api/v1/cameras.py` 和 `app/services/mediamtx.py` 中补充 Control API path 管理。

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- 可选：Docker 与 Docker Compose

## 安装依赖

```bash
cd stream-gateway
uv sync
```

`uv sync` 会根据 `pyproject.toml` 和 `uv.lock` 创建 `.venv` 并安装运行、开发依赖。

## 本地启动

在 `stream-gateway/` 目录执行：

```bash
uv run --env-file ../.env uvicorn app.main:app \
  --app-dir src \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

如果根目录尚无 `.env`：

```bash
cp ../.env.example ../.env
```

服务启动后可访问：

- OpenAPI：<http://localhost:8000/docs>
- 存活检查：<http://localhost:8000/api/v1/health/live>
- 就绪检查：<http://localhost:8000/api/v1/health/ready>

`ready` 会访问 `${MEDIAMTX_API_URL}/v3/config/paths/list`，MediaMTX 未启动或 Control API 未启用时返回 HTTP 503。

## Docker Compose 启动

在仓库根目录执行：

```bash
cp .env.example .env
docker compose up --build --wait
```

FastAPI 在 Compose 网络中通过 `http://mediamtx:9997` 访问 MediaMTX。Control API 端口不会映射到宿主机。

查看日志：

```bash
docker compose logs -f stream-gateway
```

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEDIAMTX_API_URL` | `http://mediamtx:9997` | MediaMTX Control API 内部地址 |
| `MEDIAMTX_API_TIMEOUT` | `5` | Control API 请求超时，单位为秒 |
| `PUBLIC_WEBRTC_BASE_URL` | `http://localhost:8889` | 返回给浏览器的 WebRTC 公共地址 |
| `STREAM_GATEWAY_PORT` | `8000` | 映射到宿主机的 API 端口 |
| `STREAM_GATEWAY_LOG_LEVEL` | `info` | Uvicorn 日志级别 |
| `STREAM_GATEWAY_CORS_ORIGINS` | `http://localhost:5173` | 允许的前端 Origin，多个值使用逗号分隔 |

应用不会主动读取或维护摄像头数据库。MediaMTX 当前 path 配置将作为首期运行时状态来源。

## 项目结构

```text
stream-gateway/
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── src/
│   └── app/
│       ├── main.py
│       ├── api/
│       │   ├── dependencies.py
│       │   └── v1/
│       │       ├── cameras.py
│       │       └── health.py
│       ├── core/
│       │   └── config.py
│       ├── schemas/
│       │   ├── camera.py
│       │   └── health.py
│       └── services/
│           └── mediamtx.py
└── tests/
    ├── conftest.py
    └── test_health.py
```

各层职责：

- `api`：HTTP 路由、依赖注入和状态码转换。
- `schemas`：Pydantic 请求及响应模型。
- `services`：MediaMTX 等外部系统适配器。
- `core`：应用配置和通用基础设施。
- `tests`：单元和接口测试。

## 开发命令

```bash
# 运行测试
uv run pytest

# 覆盖率
uv run pytest --cov=app --cov-report=term-missing

# 静态检查
uv run ruff check .

# 格式检查
uv run ruff format --check .

# 自动格式化
uv run ruff format .
```

添加依赖时使用 uv，不直接编辑锁文件：

```bash
uv add package-name
uv add --dev package-name
```

依赖发生变化后提交 `pyproject.toml` 和 `uv.lock`。
