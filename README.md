# SOP Vision

SOP Vision 是一个面向 IP Camera 的视觉分析平台。平台将视频接入、业务控制和视觉算法解耦：MediaMTX 负责视频路由与浏览器播放，FastAPI 负责控制面与业务 API，Detector 负责检测、Tracking 和 SOP 判断。

> 项目正在按目标架构逐步实现。当前仓库已包含 PostgreSQL、Redis、MediaMTX、FastAPI 和 Web Frontend；Detector、数据库持久化、Redis 应用客户端及完整摄像头 CRUD 尚待接入。

## 架构概览

```mermaid
flowchart LR
    CAM["IP Camera"] -->|"RTSP"| MTX["MediaMTX"]
    CAM -. "Direct RTSP（可选）" .-> DET["Detector"]
    MTX -->|"RTSP（可选）"| DET
    MTX -->|"WebRTC / WHEP"| FE["Web Frontend"]

    FE -->|"REST"| API["FastAPI"]
    API -->|"WebSocket"| FE
    API -->|"Control API"| MTX
    API -->|"gRPC"| DET

    API -->|"配置与业务数据"| PG[(PostgreSQL)]
    API <-->|"运行时状态与消息"| REDIS[(Redis)]
    DET -->|"检测结果与状态"| REDIS
```

核心分工：

| 组件         | 核心职责                                                                           |
| ------------ | ---------------------------------------------------------------------------------- |
| MediaMTX     | 接入和代理 RTSP 流，为浏览器提供 WebRTC/WHEP，并向 Detector 提供可选的统一 RTSP 源 |
| FastAPI      | 用户与权限、摄像头和算法配置、MediaMTX 管理、Detector 控制、实时结果聚合及前端 API |
| Detector     | 视频解码、检测、Tracking、SOP 判断和运行时状态上报；生命周期独立于 FastAPI         |
| PostgreSQL   | 持久化配置和业务数据，是 Desired State 的唯一事实源                                |
| Redis        | Detector 心跳、Actual State、缓存和实时消息，不承担正式配置持久化                  |
| Web Frontend | 通过 FastAPI 管理业务，通过 MediaMTX 播放视频，并叠加实时检测信息                  |

更完整的服务边界、数据模型与容错策略见[总体架构设计](docs/vision-platform-architecture.md)。

## 关键数据流

- 视频播放：`IP Camera → MediaMTX → WebRTC/WHEP → Browser`
- Detector 控制：`FastAPI → gRPC → Detector`
- 实时检测：`Detector → Redis Pub/Sub → FastAPI WebSocket → Browser`
- 可靠业务事件：`Detector → Redis Stream → FastAPI → PostgreSQL`
- 配置恢复：`PostgreSQL Desired State → Reconciler → MediaMTX / Detector Actual State`

前端只通过 FastAPI 操作业务资源，不直接访问 MediaMTX Control API、Redis、PostgreSQL 或 Detector gRPC。视频不经过 FastAPI；浏览器使用 `<video>` 播放，`<canvas>` 只绘制 bbox、ROI 和 SOP 信息。

## Detector 视频源

Detector 支持两种源模式：

- `DIRECT`：直接连接 Camera，链路最短，MediaMTX 故障不影响算法，但会增加摄像头连接数和局域网流量。
- `MEDIAMTX`：通过 MediaMTX 拉流，地址统一且适合多消费者，但 MediaMTX 会进入算法链路。

具体模式应根据摄像头 RTSP 会话上限、网络带宽、延迟和可用性要求选择。

## 架构原则

1. 视频、业务数据和算法执行相互解耦。
2. PostgreSQL 保存持久化的 Desired State，Redis 保存运行时 Actual State。
3. Command、Event、Telemetry 使用不同通信语义：gRPC、Redis Stream、Redis Pub/Sub。
4. MediaMTX 和 Detector 的实际状态由控制面根据持久化配置进行对账恢复。
5. Detector 不在算法主循环同步等待 FastAPI、Redis 或 PostgreSQL；外围服务故障时继续使用当前配置或 Last Known Good 配置。

## 当前仓库

```text
.
├── backend/                       # FastAPI 控制面（当前包含 Stream Gateway 骨架）
├── detector/                      # Detector 预留目录
├── docs/                          # 项目文档
├── frontend/                      # React、TypeScript 和 Vite 前端
├── compose.yaml                   # 完整容器构建和部署配置
├── compose.dev.yaml               # 宿主机开发所需的基础设施端口覆盖
└── .env.example
```

当前实现范围：

- FastAPI 应用、存活/就绪检查和 MediaMTX 异步客户端。
- 摄像头模型、路由及服务骨架；CRUD 尚未实现。
- React/Vite 前端应用和生产 Nginx 镜像。
- PostgreSQL、Redis 和 MediaMTX Compose 基础设施。
- MediaMTX Control API 在基础 Compose 中仅供容器网络访问，在开发覆盖中只绑定宿主机回环地址。
- PostgreSQL 已接入 Compose，但 Backend 尚未实现持久化。
- Redis 已接入 Compose，但 Backend 和 Detector 尚未实现 Redis 客户端。
- 动态 MediaMTX Path 当前属于运行时状态，服务重启后不保证保留。

## 环境配置

项目按运行位置拆分环境变量，不能把容器内部地址直接用于宿主机进程：

| 文件                  | 使用者                                               | 地址规则                                               |
| --------------------- | ---------------------------------------------------- | ------------------------------------------------------ |
| `.env`                | Docker Compose 插值、Backend/Frontend 容器构建与运行 | 使用 `postgres`、`redis`、`mediamtx` 等 Compose 服务名 |
| `backend/.env.local`  | 宿主机 Uvicorn                                       | 使用 `127.0.0.1` 和开发覆盖发布的端口                  |
| `frontend/.env.local` | 宿主机 Vite                                          | 使用浏览器可访问的 Backend 地址                        |

首次开发前创建本机配置：

```bash
cp .env.example .env
cp backend/.env.local.example backend/.env.local
cp frontend/.env.local.example frontend/.env.local
```

这些实际配置文件不会提交到 Git。修改 PostgreSQL 用户、密码或端口时，需要同步更新根 `.env` 的容器连接串和 `backend/.env.local` 的宿主机连接串。

## 日常本地开发

只在 Compose 中运行 PostgreSQL、Redis 和 MediaMTX；Backend 与 Frontend 在宿主机运行，以获得 Uvicorn 自动重载、Vite HMR 和本地调试能力。

环境要求：

- Docker 与 Docker Compose。
- Python 3.12 和 uv。
- Node.js 24 和 pnpm 11。

### 1. 安装应用依赖

首次运行或锁文件变化后执行：

```bash
cd backend
uv sync

cd ../frontend
corepack enable
pnpm install --frozen-lockfile
```

### 2. 启动基础设施

在仓库根目录执行：

```bash
docker compose -f compose.yaml -f compose.dev.yaml \
  up --wait postgres redis mediamtx
```

宿主机连接地址：

| 服务                 | 地址                                                            |
| -------------------- | --------------------------------------------------------------- |
| PostgreSQL           | `postgresql+psycopg://sop_vision:***@127.0.0.1:5432/sop_vision` |
| Redis                | `redis://127.0.0.1:6379/0`                                      |
| MediaMTX Control API | `http://127.0.0.1:9997`                                         |
| MediaMTX RTSP        | `rtsp://127.0.0.1:8554`                                         |
| MediaMTX WebRTC/WHEP | `http://127.0.0.1:8889`                                         |

### 3. 启动 Backend

新开终端，在仓库根目录执行：

```bash
cd backend
uv run --env-file .env.local uvicorn app.main:app \
  --app-dir src \
  --host 127.0.0.1 \
  --port 3001 \
  --reload
```

`uv` 在 Uvicorn 导入应用前把 `backend/.env.local` 注入进程环境；Pydantic Settings 从进程环境读取配置。Python 源码保存后由 Uvicorn 自动重启。

### 4. 启动 Frontend

再开一个终端，在仓库根目录执行：

```bash
cd frontend
pnpm dev
```

Vite 自动读取 `frontend/.env.local`，并把 `VITE_API_BASE_URL` 暴露给前端代码。React、TypeScript 和 CSS 修改通过 Vite HMR 更新浏览器。

### 5. 常用地址：

| 地址                                        | 用途                           |
| ------------------------------------------- | ------------------------------ |
| <http://127.0.0.1:8000>                     | Vite 开发服务器                |
| <http://127.0.0.1:3001/docs>                | FastAPI OpenAPI                |

### 6. 停止开发基础设施

停止容器但保留 PostgreSQL 和 Redis 数据卷：

```bash
docker compose -f compose.yaml -f compose.dev.yaml \
  stop postgres redis mediamtx
```

日常开发不要使用 `down --volumes`，该命令会删除本地 PostgreSQL 和 Redis 数据。

## Compose 全栈构建与启动

完整 Compose 使用生产式 Backend 和 Frontend 镜像：Backend 运行 Uvicorn 且不启用自动重载，Frontend 构建为静态资源并由 Nginx 提供。

### 1. 验证配置

```bash
test -f .env || cp .env.example .env
docker compose --env-file .env config
```

### 2. 构建镜像

```bash
docker compose --env-file .env build
```

只重建应用镜像：

```bash
docker compose --env-file .env build backend frontend
```

### 3. 启动完整服务

```bash
docker compose --env-file .env up --wait
```

此命令启动 PostgreSQL、Redis、MediaMTX、Backend 和 Frontend，并等待带健康检查的服务就绪。

### 4. 代码或配置变更后的重建

容器版 Backend 和 Frontend 不挂载宿主机源码，不支持热重载。修改 Backend 源码后重建 Backend；修改 Frontend 源码或 `FRONTEND_API_BASE_URL` 后重建 Frontend：

```bash
docker compose --env-file .env build backend frontend
docker compose --env-file .env up --wait backend frontend
```

`FRONTEND_API_BASE_URL` 会作为 Vite build arg 静态写入前端产物，仅重启 Frontend 容器不会更新该地址。

### 5. 停止完整服务

```bash
docker compose down
```

该命令保留命名数据卷。只有明确需要清空 PostgreSQL 和 Redis 数据时才使用 `docker compose down --volumes`。

局域网部署时，需要在 `.env` 中将 `MTX_WEBRTCADDITIONALHOSTS` 和 `PUBLIC_WEBRTC_BASE_URL` 配置为浏览器实际可达的宿主机 IP 或域名。容器之间通过 Compose 服务名通信，不使用 `localhost`。

## 质量检查

Backend：

```bash
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Frontend：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

Backend 模块说明和配置项见 [Backend README](backend/README.md)。
