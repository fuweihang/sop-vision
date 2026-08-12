# SOP Vision

SOP Vision 是一个面向 IP 摄像头的轻量视频接入原型。当前 MVP 使用 Docker Compose 运行 MediaMTX、Backend 和前端应用：Backend 基于 FastAPI，其中的 Stream Gateway 模块对 MediaMTX Control API 做一层业务封装，用于动态绑定或解绑 RTSP 摄像头；前端通过 WebRTC（WHEP）播放 MediaMTX 输出的视频流。

> 当前仓库处于初始化阶段。Compose 已提供 PostgreSQL 基础设施，但 Backend 的数据库持久化和事件存储尚未实现。

## MVP 目标

- 使用一条 `docker compose up` 命令启动全部服务。
- 通过 FastAPI REST 接口添加、查询、更新和删除摄像头。
- FastAPI 通过 Docker 内部网络访问 MediaMTX Control API。
- MediaMTX 按需拉取摄像头 RTSP 流，并通过 WebRTC/WHEP 提供浏览器播放能力。
- 前端展示摄像头列表，并使用 `<video>` 播放选中的 WebRTC 流。
- PostgreSQL 已加入 Compose；在 Gateway 完成持久化实现前，动态配置仍只视为运行时状态，服务重启后不保留。

## 系统架构

```mermaid
flowchart LR
    CAM["IP 摄像头"] -->|"RTSP"| MTX["MediaMTX"]
    MTX -->|"WHEP 信令 :8889<br/>WebRTC 媒体 :8189/udp"| WEB
    API -->|"Docker 网络 / Control API :9997"| MTX
    API -.->|"配置持久化（待实现）"| DB["PostgreSQL"]
    WEB["浏览器前端"] -->|"REST"| API["FastAPI"]
```

三类访问地址需要严格区分：

| 调用方 | 目标 | 地址示例 | 说明 |
| --- | --- | --- | --- |
| FastAPI 容器 | MediaMTX Control API | `http://mediamtx:9997` | 使用 Compose 服务名，仅在容器网络内可达 |
| 浏览器 | FastAPI | `http://localhost:8000/api/v1` | 由宿主机映射端口访问 |
| 浏览器 | MediaMTX WebRTC | `http://localhost:8889/cameras/{camera_id}/whep` | 浏览器不能解析 `mediamtx` 服务名 |

## 技术栈

- 容器编排：Docker Compose
- 数据库：PostgreSQL 17
- 媒体服务：MediaMTX 1.x
- 后端：Python、FastAPI、Pydantic；业务能力按模块组织
- 前端：Vite、TypeScript（具体 UI 框架可在实现时确定）
- 播放协议：WebRTC / WHEP
- 摄像头输入：RTSP，首期优先支持 H.264

## 目录结构

```text
.
├── .env.example
├── compose.yaml
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/
│   │   └── app/
│   │       ├── main.py
│   │       ├── core/
│   │       └── modules/
│   │           └── stream_gateway/
│   │               ├── api/
│   │               ├── schemas/
│   │               └── services/
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── api/
│       ├── components/
│       └── pages/
├── mediamtx/
│   └── mediamtx.yml        # 旧配置参考，Compose 不挂载
└── docs/
```

## 服务与端口

| 服务 | 容器端口 | 是否映射到宿主机 | 用途 |
| --- | ---: | --- | --- |
| `frontend` | `5173` 或 `80` | 是 | Web 页面 |
| `backend` | `8000/tcp` | 是 | 后端 API 和 OpenAPI 文档（含 Stream Gateway 模块） |
| `postgres` | `5432/tcp` | 仅宿主机回环地址 | Backend 配置持久化（待实现） |
| `mediamtx` | `8554/tcp` | 按需 | RTSP 输入/调试 |
| `mediamtx` | `8889/tcp` | 是 | WebRTC HTTP/WHEP 信令 |
| `mediamtx` | `8189/udp` | 是 | WebRTC ICE/媒体传输 |
| `mediamtx` | `9997/tcp` | 否 | Control API，仅供内部服务调用 |

MediaMTX 配置全部通过环境变量注入，不额外挂载 `mediamtx.yml`。环境变量遵循 `MTX_参数名大写` 的命名规则，数组参数使用逗号分隔：

```dotenv
# 启用仅供 FastAPI 调用的 Control API
MTX_API=yes
MTX_APIADDRESS=:9997

# 启用浏览器 WebRTC/WHEP 播放
MTX_WEBRTC=yes
MTX_WEBRTCADDRESS=:8889
MTX_WEBRTCLOCALUDPADDRESS=:8189

# 数组使用逗号分隔；填写浏览器能够访问到的宿主机地址
MTX_WEBRTCADDITIONALHOSTS=127.0.0.1,192.168.1.100
```

Compose 的 `.env` 文件默认只参与变量插值，不会自动把全部变量注入容器，因此 `compose.yaml` 需要显式传递这些变量。PostgreSQL 使用命名卷 `postgres-data` 保存数据，Backend 通过 `DATABASE_URL` 连接数据库：

```yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: sop_vision
      POSTGRES_USER: sop_vision
      POSTGRES_PASSWORD: change-me

  backend:
    environment:
      DATABASE_URL: postgresql://sop_vision:change-me@postgres:5432/sop_vision

  mediamtx:
    image: bluenviron/mediamtx:1
    environment:
      MTX_API: "${MTX_API:-yes}"
      MTX_APIADDRESS: "${MTX_APIADDRESS:-:9997}"
      MTX_WEBRTC: "${MTX_WEBRTC:-yes}"
      MTX_WEBRTCADDRESS: "${MTX_WEBRTCADDRESS:-:8889}"
      MTX_WEBRTCLOCALUDPADDRESS: "${MTX_WEBRTCLOCALUDPADDRESS:-:8189}"
      MTX_WEBRTCADDITIONALHOSTS: "${MTX_WEBRTCADDITIONALHOSTS:-127.0.0.1}"
    ports:
      - "${MEDIAMTX_RTSP_PORT:-8554}:8554"
      - "${MEDIAMTX_WEBRTC_PORT:-8889}:8889"
      - "${MEDIAMTX_WEBRTC_UDP_PORT:-8189}:8189/udp"
    expose:
      - "9997"
```

`expose` 用于记录 `9997` 是容器内部端口；由于没有对应的 `ports` 映射，Control API 不会发布到宿主机。生产或局域网部署时，`MTX_WEBRTCADDITIONALHOSTS` 必须包含浏览器实际可达的宿主机 IP 或域名，而不是容器 IP。

## 摄像头 API 约定

FastAPI 提供稳定的业务接口，隐藏 MediaMTX Control API 的具体格式。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/cameras` | 添加摄像头并创建 MediaMTX path |
| `GET` | `/api/v1/cameras` | 查询当前运行时摄像头列表 |
| `GET` | `/api/v1/cameras/{camera_id}` | 查询摄像头配置和在线状态 |
| `PATCH` | `/api/v1/cameras/{camera_id}` | 修改名称或 RTSP 地址 |
| `DELETE` | `/api/v1/cameras/{camera_id}` | 删除摄像头并移除 MediaMTX path |
| `GET` | `/api/v1/health/live` | FastAPI 存活检查 |
| `GET` | `/api/v1/health/ready` | FastAPI 与 MediaMTX 连通性检查 |

添加摄像头：

```bash
curl -X POST http://localhost:8000/api/v1/cameras \
  -H 'Content-Type: application/json' \
  -d '{
    "camera_id": "entrance-01",
    "name": "一号门入口",
    "source_url": "rtsp://username:password@192.168.1.20:554/stream1"
  }'
```

预期响应：

```json
{
  "camera_id": "entrance-01",
  "name": "一号门入口",
  "path": "cameras/entrance-01",
  "status": "configured",
  "whep_url": "http://localhost:8889/cameras/entrance-01/whep"
}
```

`camera_id` 建议只允许小写字母、数字和连字符，避免路径冲突。接口响应、日志和错误信息不得返回包含用户名或密码的完整 RTSP URL。

### Control API 映射

FastAPI 内部将业务操作映射到 MediaMTX v3 配置接口：

| 业务操作 | MediaMTX 请求 |
| --- | --- |
| 添加 | `POST /v3/config/paths/add/cameras/{camera_id}` |
| 更新 | `PATCH /v3/config/paths/patch/cameras/{camera_id}` |
| 删除 | `DELETE /v3/config/paths/delete/cameras/{camera_id}` |
| 查询配置 | `GET /v3/config/paths/list` |
| 查询运行状态 | `GET /v3/paths/list` |

添加 path 时发送给 MediaMTX 的核心配置如下：

```json
{
  "source": "rtsp://username:password@192.168.1.20:554/stream1",
  "sourceOnDemand": true
}
```

`sourceOnDemand` 让 MediaMTX 在出现读取者时再连接摄像头，适合首期按需预览场景。FastAPI 应设置调用超时，并将 MediaMTX 的连接失败、重复 path 和 path 不存在等错误转换为稳定的 HTTP 状态码。

## 前端播放

前端的最小功能包括：

1. 从 `GET /api/v1/cameras` 获取摄像头列表。
2. 选择摄像头后，用返回的 `whep_url` 建立 WebRTC 播放会话。
3. 将 MediaStream 绑定到 `<video autoplay muted playsinline>`。
4. 展示连接中、播放中、断流和重连状态。
5. 切换摄像头或离开页面时关闭旧的 `RTCPeerConnection`。

前端只通过 FastAPI 管理摄像头，但视频数据直接由 MediaMTX 发送到浏览器，避免视频流经过 FastAPI。

## 配置项

计划通过 `.env` 提供以下配置：

```dotenv
# MediaMTX 原生配置
MTX_API=yes
MTX_APIADDRESS=:9997
MTX_WEBRTC=yes
MTX_WEBRTCADDRESS=:8889
MTX_WEBRTCLOCALUDPADDRESS=:8189
MTX_WEBRTCADDITIONALHOSTS=127.0.0.1

# FastAPI 容器内部使用
MEDIAMTX_API_URL=http://mediamtx:9997

# 返回给浏览器，必须是浏览器可访问的地址
PUBLIC_WEBRTC_BASE_URL=http://localhost:8889

# Backend 服务配置
BACKEND_PORT=8000
BACKEND_LOG_LEVEL=info
BACKEND_CORS_ORIGINS=http://localhost:5173

# 前端访问 Backend
VITE_BACKEND_API_BASE_URL=http://localhost:8000/api/v1
```

不要提交真实摄像头地址或凭据；本项目的 `.gitignore` 已忽略 `.env`，仓库只保留脱敏的 `.env.example`。

## 启动与验证

完成各服务实现后，统一使用以下命令启动：

```bash
cp .env.example .env
docker compose config
docker compose up --build --wait
```

验证服务：

```bash
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/cameras
```

常用排查命令：

```bash
docker compose ps
docker compose logs -f backend mediamtx
```

停止服务：

```bash
docker compose down
```

## 暂不持久化的行为

PostgreSQL 服务目前只完成基础设施接入，FastAPI 尚未读写数据库。MediaMTX 的当前运行时配置仍是唯一状态来源：

- FastAPI 重启后，重新从 MediaMTX 查询现有 path。
- MediaMTX 或整个 Compose 项目重启后，动态添加的摄像头可能丢失，需要重新调用添加接口。
- 不实现跨重启恢复、历史记录、审计日志或多实例一致性。
- 后续接入数据库时，由 Controller 将数据库中的期望状态与 MediaMTX 运行状态进行对账恢复。

## 安全边界

当前 MVP 默认只用于开发环境或受信任的局域网：

- 不把 `9997` Control API 映射到宿主机。
- 不在日志、异常和 API 响应中输出 RTSP 凭据。
- 对 `camera_id`、URL scheme 和请求体长度进行校验。
- 为 FastAPI 到 MediaMTX 的请求设置连接与读取超时。
- 摄像头和 MediaMTX 之间优先使用隔离的视频网络。
