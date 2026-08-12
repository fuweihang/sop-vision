# IP Camera 视觉平台总体架构设计

## 1. 架构目标

本系统由三个核心后端服务组成：

- **服务 A：MediaMTX**
  - 统一接管 IP Camera 视频流。
  - 对摄像头原始 RTSP 流进行代理、路由和协议转换。
  - 对前端提供 WebRTC/WHEP 视频播放能力。
  - 对 Worker 提供可选的 RTSP 中转源。
- **服务 B：FastAPI**
  - 平台控制面和业务服务。
  - 封装 MediaMTX Control API，禁止前端直接操作 MediaMTX 管理接口。
  - 提供摄像头、Worker、算法配置、用户、权限、业务数据等 REST API。
  - 聚合 Worker 的实时检测结果，通过 WebSocket 推送给前端。
- **服务 C：Vision Worker**
  - 核心视觉算法服务。
  - 执行视频解码、检测、Tracking、SOP 判断等任务。
  - 视频源可配置为直接连接 IP Camera，或通过 MediaMTX 拉流。
  - 核心算法运行生命周期独立于 FastAPI，FastAPI 停止不应导致 Worker 停止。

系统总体原则：

> **MediaMTX 负责视频，FastAPI 负责控制与业务，Worker 负责算法，PostgreSQL 保存持久化业务状态，Redis 承担运行时状态和实时消息。**

---

## 2. 总体架构

![总体架构图](./assets/vision-platform-architecture.png)

### Mermaid 简化图

```mermaid
flowchart LR
    CAM[IP Camera]
    MTX[MediaMTX A]
    API[FastAPI B]
    WK[Vision Worker C]
    PG[(PostgreSQL)]
    R[(Redis)]
    FE[Web Frontend]

    CAM -->|RTSP| MTX
    CAM -. 可选 Direct RTSP .-> WK
    MTX -->|RTSP 可选源| WK
    MTX -->|WebRTC / WHEP| FE

    FE -->|REST| API
    API -->|WebSocket| FE

    API -->|Control API| MTX
    API -->|gRPC| WK

    API -->|业务配置 / Desired State| PG
    API -->|Runtime / Cache / Messaging| R
    WK -->|Realtime Detection / Runtime State| R
    WK -->|Durable Events| R

    R -->|消费检测数据| API
```

---

## 3. 服务职责边界

### 3.1 MediaMTX A

MediaMTX 是整个系统的媒体路由层，而不是业务层。

主要职责：

1. 接收或主动拉取 IP Camera RTSP 视频流。
2. 为每个摄像头维护稳定的逻辑 Path，例如：

```text
camera_001
camera_002
camera_wash_area_01
```

3. 将同一路视频提供给不同消费者：

```text
IP Camera
    │
    ▼
MediaMTX
    ├── RTSP ─────► Vision Worker
    └── WebRTC ───► Browser
```

4. 通过 Control API 提供动态 Path 配置和运行状态查询。
5. MediaMTX Control API 只应在内网暴露，由 FastAPI 调用。

MediaMTX **不负责**：

- 用户权限。
- 摄像头业务数据持久化。
- 算法逻辑。
- bbox 绘制。
- SOP 业务流程。

---

## 4. FastAPI B

FastAPI 是平台的 **Control Plane**。

主要职责：

- 用户认证和 RBAC。
- IP Camera CRUD。
- MediaMTX Path 管理。
- Worker 配置管理。
- 算法参数管理。
- ROI / SOP 配置。
- PostgreSQL 数据持久化。
- Worker 实时状态聚合。
- Redis 消息消费。
- WebSocket Gateway。
- 对前端隐藏内部基础设施细节。

前端不直接操作：

```text
MediaMTX Control API
Redis
PostgreSQL
Worker gRPC Server
```

统一经过：

```text
Frontend → FastAPI
```

---

## 5. Vision Worker C

Worker 是系统中优先级最高的算法执行服务。

典型内部模块：

```text
Vision Worker
├── Camera / Stream Manager
├── Decoder
├── Detector (YOLO 等)
├── Tracker
├── SOP Engine
├── Runtime State Manager
├── Event Publisher
└── gRPC Control Server
```

### 5.1 视频源模式

Worker 支持两种 Source Mode：

```text
DIRECT
MEDIAMTX
```

#### DIRECT

```text
IP Camera ──RTSP──► Worker
```

优势：

- 最短链路。
- MediaMTX 故障不影响算法。
- 理论延迟最低。

缺点：

- Camera 同时需要承担 MediaMTX 和 Worker 两个 RTSP Client。
- 摄像头和局域网流量增加。

#### MEDIAMTX

```text
IP Camera ──RTSP──► MediaMTX ──RTSP──► Worker
```

优势：

- Camera 通常只需一个上游连接。
- 流地址统一。
- 更适合多 Worker、多消费者和大规模摄像头。

缺点：

- MediaMTX 进入 Worker 的视频 Critical Path。
- MediaMTX 故障会影响 Worker 获取视频。
- 同机纯转发预计只增加少量延迟，但仍需实际压测。

Worker 不应该在算法主循环同步等待 Redis、FastAPI 或 PostgreSQL。

推荐结构：

```text
Video Pipeline
    │
    ├── inference
    ├── tracking
    └── bounded queue
             │
             ▼
       Async Publisher
             │
             ▼
           Redis
```

---

## 6. PostgreSQL 和 Redis 的职责

### 6.1 PostgreSQL：业务配置唯一事实源

PostgreSQL 应作为：

> **Persistent / Desired State Source of Truth**

适合存储：

- 用户。
- Role / Permission。
- 摄像头定义。
- 摄像头原始 RTSP 地址。
- MediaMTX Path。
- Worker Source Mode。
- Worker / Camera 绑定关系。
- ROI。
- 模型配置。
- SOP 配置。
- 告警规则。
- 检测业务事件历史。
- 操作审计日志。

不建议将这些正式配置只保存在 Redis。

### 6.2 Redis：运行时状态和消息总线

Redis 适合：

- Worker heartbeat。
- Worker 当前状态。
- Camera 实时状态。
- FPS / latency / 当前人数。
- bbox / tracking realtime metadata。
- Redis Pub/Sub。
- Redis Stream。
- 临时缓存。

推荐原则：

```text
PostgreSQL = Desired / Persistent State
Redis      = Actual / Runtime / Messaging State
```

---

## 7. 推荐 Camera 数据模型

第一版可以保持简单：

```text
camera
────────────────────────────────
id
name
source_rtsp_url
mtx_path
enabled
worker_source_mode
config_version
created_at
updated_at
```

例如：

```json
{
  "id": "cam_001",
  "name": "洗手区",
  "source_rtsp_url": "rtsp://user:***@192.168.1.20/...",
  "mtx_path": "cam_001",
  "enabled": true,
  "worker_source_mode": "MEDIAMTX",
  "config_version": 18
}
```

后续复杂后可拆分：

```text
camera
camera_stream
worker_camera_binding
algorithm_config
roi_config
sop_config
```

### 凭证安全

摄像头密码不应原样返回给前端。

推荐：

- DB 中加密保存密码，或使用 Secret 管理系统。
- API 返回脱敏 URL。
- 前端仅提交新密码，不读取原密码。

---

## 8. MediaMTX 配置流程

不推荐把 MediaMTX 本身当配置数据库。

推荐：

```text
Frontend
   │
   ▼
FastAPI
   │
   ▼
PostgreSQL
Desired Config
   │
   ▼
Reconciler
   │
   ▼
MediaMTX Control API
   │
   ▼
Actual Path
```

这样即使 MediaMTX：

- Container 被删除。
- 配置丢失。
- 重启。
- 升级。

FastAPI 也可以根据 PostgreSQL 重新恢复 MediaMTX Path。

建议实现轻量的 **Reconciliation** 机制：

```text
DB Desired State
       ↓ compare
MTX Actual State
       ↓
Create / Patch / Delete
```

---

## 9. Worker 配置模型

Worker 配置同样推荐采用 Desired / Actual State。

### PostgreSQL Desired State

```text
cam_001
────────────────────
enabled = true
source_mode = MEDIAMTX
model = employee-v3
threshold = 0.65
config_version = 19
```

### Redis Actual State

```text
cam_001
────────────────────
status = RUNNING
source_mode = MEDIAMTX
applied_version = 19
fps = 24.8
latency_ms = 45
```

前端即可判断：

```text
Desired Version == Applied Version
```

如果不同：

```text
Desired v20
Actual  v19
```

UI 显示：

```text
配置待应用 / 应用失败
```

而不是只显示模糊的 online/offline。

---

## 10. Worker 控制：推荐 gRPC

Worker 的即时控制建议使用：

```text
FastAPI ──gRPC──► Worker
```

适合操作：

- StartCamera。
- StopCamera。
- ReloadCamera。
- ApplyConfig。
- ReloadModel。
- Snapshot。
- GetStatus。

优势：

- Request / Response 语义自然。
- 可以明确返回 success / error。
- 支持 timeout / deadline。
- 支持强类型接口。
- 后续多 Worker 仍然容易扩展。

例如：

```text
Frontend
   │ PUT camera config
   ▼
FastAPI
   │
   ├── PostgreSQL: version 18 → 19
   │
   └── gRPC ApplyConfig(cam_001, version=19)
                      │
                      ▼
                   Worker
                      │
                      ▼
                applied_version=19
```

### 为什么不推荐所有控制都放 Redis Stream

消息可靠不等于控制语义正确。

例如：

```text
10:00 stop_camera
Worker offline
10:10 用户重新启用
10:20 Worker online
```

如果 Worker 恢复后消费旧的 `stop_camera`，可能执行过期命令。

因此：

```text
配置状态 → PostgreSQL
即时控制 → gRPC
可靠事件 → Redis Stream
```

如果未来确实需要离线命令队列，则需要至少增加：

```text
command_id
config_version
expires_at
idempotency_key
```

---

## 11. Worker → FastAPI 检测数据

建议将 Worker 输出分为两类。

### 11.1 高频 Realtime Telemetry

包括：

- bbox。
- track position。
- FPS。
- GPU / inference latency。
- 当前人数。

特点：旧数据价值极低。

推荐：

```text
Worker
   │
   ▼
Redis Pub/Sub
   │
   ▼
FastAPI
   │
   ▼
WebSocket
   │
   ▼
Frontend Canvas
```

### 11.2 Durable Business Event

包括：

- SOP violation。
- washing completed。
- washing timeout。
- restricted zone entered。
- alarm。

推荐：

```text
Worker
   │
   ▼
Redis Stream
   │
   ▼
FastAPI Consumer Group
   │
   ├── PostgreSQL
   └── WebSocket → Frontend
```

Redis Stream 可以用于 ACK / Pending / Retry 等可靠事件消费。

---

## 12. Redis Key / Channel 建议

```text
vision:worker:{worker_id}:heartbeat
vision:worker:{worker_id}:status

vision:camera:{camera_id}:runtime
vision:camera:{camera_id}:telemetry

vision:telemetry:{camera_id}          # Pub/Sub
vision:events                          # Stream
```

Heartbeat 示例：

```json
{
  "worker_id": "vision-01",
  "status": "RUNNING",
  "uptime": 38291,
  "camera_count": 8,
  "gpu_usage": 62,
  "timestamp": 1786501200123
}
```

使用 TTL：

```text
SET vision:worker:vision-01:heartbeat ... EX 10
```

---

## 13. 前端视频与检测框协作

前端视频不经过 FastAPI：

```text
MediaMTX ──WebRTC/WHEP──► Browser <video>
```

检测数据：

```text
Worker → Redis → FastAPI ──WebSocket──► Browser <canvas>
```

最终浏览器：

```text
┌────────────────────────────┐
│ <video>                    │
│   MediaMTX WebRTC          │
│                            │
│ <canvas> overlay           │
│   bbox / ROI / SOP info    │
└────────────────────────────┘
```

推荐不要将视频帧通过 `drawImage()` 全量复制到 Canvas。

应该：

```text
video = 浏览器/GPU负责视频渲染
canvas = 只负责画框和文字
```

---

## 14. Detection Metadata 协议

每批检测结果建议至少包含：

```json
{
  "type": "frame_detection",
  "camera_id": "cam_001",
  "frame_id": 18272,
  "frame_ts": 1786501200123,
  "source_width": 1920,
  "source_height": 1080,
  "detections": [
    {
      "track_id": 12,
      "class": "person",
      "confidence": 0.96,
      "bbox": [0.21, 0.11, 0.48, 0.91]
    }
  ]
}
```

推荐 bbox 使用：

```text
normalized coordinates [0, 1]
```

而不是固定像素值。

必须保留：

```text
camera_id
frame_id
frame_ts
```

为后续视频帧与 bbox 时间同步提供基础。

---

## 15. 视频与 bbox 同步

两条数据路径不同：

```text
Video:
Camera → MediaMTX → WebRTC → Browser

Detection:
Camera/MTX → Worker → YOLO → Redis → FastAPI → WebSocket → Browser
```

延迟不会完全一致。

因此不要把协议设计成：

```text
收到 bbox → 立即无条件画
```

从第一版开始建议保留原始帧时间：

```text
frame_ts
```

后续可以实现：

- 前端小型 jitter buffer。
- 根据 frame timestamp 匹配视频。
- tracker motion prediction。
- WebCodecs / WebRTC Insertable Streams 等更精细方案。

第一版对于 SOP / 工业行为检测，可以先接受少量 overlay delay，再通过实测决定是否需要帧级同步。

---

## 16. Worker 的 Last Known Good 配置

这是核心 Worker 高可用设计中很重要的一点。

需求：

```text
FastAPI 停止
Redis 停止
PostgreSQL 暂时不可用
```

不应该使 Worker 正在运行的视觉任务停止。

因此 Worker 成功应用配置后，应保留本地：

```text
Last Known Good Config
```

可以使用：

```text
/var/lib/vision/config.json
```

或者：

```text
SQLite
```

建议逻辑：

```text
Worker 正常运行
   │
   ├── 外部配置服务可用 → 同步新配置
   │
   └── 外部服务不可用 → 继续使用当前/LKG配置
```

Worker 重启时：

```text
优先获取最新配置
   │
   └── 失败 → 使用 Last Known Good
```

---

## 17. 服务故障影响矩阵

| 故障组件 | 预期影响 |
|---|---|
| Frontend | Worker 和 MediaMTX 继续运行 |
| FastAPI | Worker 继续运行，MTX 继续已有流，UI 管理暂不可用 |
| PostgreSQL | Worker 当前任务继续运行，新业务配置暂不可保存 |
| Redis | Worker 当前算法继续运行，但 realtime/event delivery 暂停 |
| MediaMTX | WebRTC 停止；MEDIAMTX Source Mode Worker 会断流；DIRECT Worker 不受影响 |
| Worker | 对应算法任务停止，MediaMTX 视频播放仍可继续 |
| IP Camera | 对应视频和算法停止 |

这也是保留 `DIRECT / MEDIAMTX` 两种 Worker Source Mode 的重要价值。

---

## 18. Docker Compose 建议

逻辑结构：

```text
docker compose
├── mediamtx
├── backend-fastapi
├── vision-worker
├── redis
└── postgres
```

服务之间通过 Compose DNS：

```text
backend-fastapi → mediamtx:9997
backend-fastapi → vision-worker:50051
backend-fastapi → redis:6379
backend-fastapi → postgres:5432
vision-worker   → mediamtx:8554
vision-worker   → redis:6379
```

不要通过 `localhost` 调用另一个容器。

每个核心服务应该有独立 lifecycle，例如：

```yaml
restart: unless-stopped
```

不要让 FastAPI 使用 subprocess 启动 Worker。

---

## 19. 仍需重点考虑的细节

### 19.1 配置版本与幂等

至少为算法配置引入：

```text
config_version
```

Worker 只接受比当前 Applied Version 更新的配置。

控制 API 尽量实现幂等。

### 19.2 多 Worker 调度

未来如果出现：

```text
vision-worker-01
vision-worker-02
vision-worker-03
```

需要增加：

- Worker registry。
- Camera → Worker assignment。
- GPU load awareness。
- Worker failover。
- Camera task ownership lease。

此时 NATS / JetStream 等消息基础设施可能比 Redis 更有吸引力，但当前单机或少量 Worker 阶段没有必要提前复杂化。

### 19.3 可观测性

建议监控：

MediaMTX：

- active paths。
- active readers。
- bytes received/sent。
- RTSP packet loss / jitter。
- WebRTC sessions。

Worker：

- FPS。
- decode latency。
- inference latency。
- queue size。
- frame drop count。
- Redis publish error。
- reconnect count。
- GPU memory/utilization。

FastAPI：

- API latency。
- WebSocket connections。
- Redis consumer lag。
- gRPC failures。
- reconciliation failures。

### 19.4 Backpressure

高频 bbox 不能无限排队。

对于 realtime telemetry：

```text
queue full → drop old frame
```

通常比积压更正确。

对于 durable events：

```text
不能随意 drop
```

应进入可靠事件队列。

### 19.5 时钟同步

如果 MediaMTX、Worker、Camera 未来跨服务器部署，需要：

```text
NTP / Chrony
```

统一时钟，否则 `frame_ts` 很难用于跨节点同步。

### 19.6 摄像头连接与网络容量

DIRECT 模式会增加 Camera RTSP session 和 LAN 流量。

MEDIAMTX 模式减少 Camera connection，但增加服务器内部转发，并使 MTX 进入算法 critical path。

应根据：

- Camera 数量。
- Camera 最大 RTSP session。
- 单流 bitrate。
- NIC 带宽。
- Worker 数量。
- MTX 高可用要求。

做最终部署选择。

---

## 20. 推荐技术决策总结

| 场景 | 推荐技术 |
|---|---|
| 视频入口 / 路由 | MediaMTX |
| Browser 视频 | WebRTC / WHEP |
| MTX 管理 | FastAPI → MediaMTX Control API |
| Persistent Config | PostgreSQL |
| Business Data | PostgreSQL |
| Desired State | PostgreSQL |
| Runtime State | Redis Key |
| Heartbeat | Redis Key + TTL |
| Realtime bbox | Redis Pub/Sub |
| Durable Event | Redis Stream |
| Worker 即时控制 | gRPC |
| Browser 实时 metadata | FastAPI WebSocket |
| Worker fallback config | Local JSON / SQLite |

---

## 21. 最终推荐架构原则

最终可以归纳为五条：

1. **视频和业务数据完全解耦。**
   - MediaMTX 传视频。
   - Worker 产生 metadata。
   - FastAPI 传业务 metadata。

2. **PostgreSQL 是配置事实源。**
   - Redis 不承担正式持久化配置数据库职责。

3. **Desired State 与 Actual State 分离。**
   - PostgreSQL 保存 Desired State。
   - Redis 保存 Runtime / Actual State。

4. **Command、Event、Telemetry 使用不同通信语义。**

```text
Command   → gRPC
Event     → Redis Stream
Telemetry → Redis Pub/Sub
State     → Redis Key
```

5. **Worker 的核心算法不能同步依赖外围系统。**

```text
FastAPI ×
Redis   ×
DB      ×

Worker 当前视觉任务仍应尽可能继续运行。
```

这套架构适合当前单机 Docker Compose 部署，同时保留未来扩展到多 Worker、多 GPU 节点和多服务器部署的空间。
