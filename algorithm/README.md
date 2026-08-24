# SOP Vision Algorithm

`algorithm` 是 SOP Vision 的算法服务。外部客户端把任务参数保存到 PostgreSQL，再只携带
`task_id` 调用 Algorithm Daemon；守护进程从数据库读取并严格校验配置，在有界独立进程池
中运行 AIWorker。Detector 从 RTSP 拉流、执行 YOLO，并把检测元数据直接写入 Redis。

## 架构

```text
                         GET JSON Schema
Qt / 平台客户端 <──────────────────────── Algorithm Daemon
      │                                      ▲
      │ UPSERT task_id/type/config           │ start/reload/stop(task_id)
      ▼                                      │
PostgreSQL ───────────读取已提交配置───────────┘
                                               │ spawn/Event/Pipe
                                               ▼
RTSP ─────────────────────────────────────> AIWorker ──> Redis
  └────────────────────> Qt Viewer <────────────┘
```

- PostgreSQL 是唯一任务配置源，不再读取 `config.json`。
- 守护进程不自动启动或自动重启 Worker，也不持久化运行状态。
- Worker 进程池默认最多同时运行 4 个任务，容量耗尽时 `start` 返回 429。
- Qt Viewer 同时承担外部客户端模拟、Worker 控制和检测结果预览。

## 安装与数据库迁移

要求 Python 3.12，推荐使用 `uv`：

```bash
uv sync --dev
uv sync --dev --extra viewer   # 需要 Qt Viewer 时
```

根目录 Compose 已提供 PostgreSQL，默认宿主机连接信息为：

```text
postgresql://sop_vision:sop_vision@localhost:5432/sop_vision
```

首次使用或版本升级时运行 Alembic：

```bash
docker compose up -d postgres
cd algorithm
ALGORITHM_DATABASE_URL=postgresql://sop_vision:sop_vision@localhost:5432/sop_vision \
  uv run alembic upgrade head
```

迁移创建 `worker_task_parameters`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | `TEXT` 主键 | 外部系统提供的任务 ID |
| `worker_type` | `TEXT` | 注册表中的 Worker 类型 |
| `config` | `JSONB` | 不含 `task_id` 的参数对象 |
| `updated_at` | `TIMESTAMPTZ` | 数据库触发器维护的最后更新时间 |

客户端必须先提交 UPSERT 事务，再调用 Daemon。数据库只约束 JSON 顶层结构；具体字段由
对应 Worker 的 Pydantic 模型在启动时再次校验。

## 配置

```dotenv
ALGORITHM_DATABASE_URL=postgresql://sop_vision:sop_vision@localhost:5432/sop_vision
ALGORITHM_MAX_WORKERS=4
ALGORITHM_RESOURCE_ROOT=/absolute/path/to/sop-vision/algorithm
```

相对模型路径以 `ALGORITHM_RESOURCE_ROOT` 为基准；未设置时使用安装包所在的 algorithm
工程根目录。配置和错误日志不会回显 RTSP、Redis 或数据库凭据。

当前 Detector 参数示例（存入 `config` 列）：

```json
{
  "rtsp_url": "rtsp://user:password@camera/stream",
  "redis_url": "redis://127.0.0.1:63793/0",
  "model_path": "resources/models/yolo26n.pt",
  "image_size": 640,
  "confidence": 0.5,
  "device": "0",
  "reconnect_delay_seconds": 2.0,
  "roi": {
    "roi_id": "main",
    "points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
  }
}
```

`roi=null` 表示全画面检测。ROI 坐标归一化到 `[0, 1]`，至少需要三个不重复且能组成
非零面积多边形的点。

## 启动与控制

```bash
uv run algorithm-daemon --host 127.0.0.1 --port 8090
```

配置发现：

```bash
curl http://127.0.0.1:8090/v1/worker-types
curl http://127.0.0.1:8090/v1/worker-types/detector/schema
```

控制命令只接受空请求体：

```bash
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/start
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/reload
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/stop
curl http://127.0.0.1:8090/healthz
```

- `start`：读取数据库最新配置并启动；任务已运行时返回 409。
- `reload`：先验证数据库最新配置，再停止旧 Worker 并启动新 Worker；配置无效时旧进程
  继续运行。
- `stop`：优雅停止，超时后 terminate/kill；已配置但未运行的任务幂等成功。

404 表示任务或类型不存在，422 表示配置非法，429 表示进程容量耗尽，503 表示数据库
不可用，504 表示 Worker 未在期限内就绪。命令同步等待模型加载与主循环就绪。

绕过守护进程调试单个 Detector 时也从数据库读取：

```bash
uv run detector --task-id detector-001
```

## Qt Viewer 外部客户端模拟

```bash
uv run --extra viewer algorithm-viewer \
  --task-id detector-001 \
  --daemon-url http://127.0.0.1:8090 \
  --database-url postgresql://sop_vision:sop_vision@localhost:5432/sop_vision
```

Viewer 从 Daemon 获取 Worker 类型与标准 JSON Schema，动态生成参数控件并执行客户端
校验。它可从数据库加载已有任务，也可使用“保存并启动”或“保存并重载”先 UPSERT 参数、
再调用控制命令。Detector 启动成功后，Viewer 自动使用配置中的 RTSP/Redis 地址连接预览。
界面采用可拖动的左右分栏：左侧编辑任务参数，右侧显示视频；Daemon 和数据库连接地址
位于默认收起的“高级连接设置”中。Viewer 不提供独立的 RTSP/Redis 覆盖输入，数据库任务
配置是预览地址的唯一来源。
当任务配置包含 ROI 时，Viewer 会在视频内容区域绘制黄色虚线多边形并标注区域 ID；
`roi=null` 时不绘制边框。多边形仅用于展示当前过滤区域，不改变 Worker 的中心点过滤规则。

Viewer 不做 RTP/RTCP/PTS 时间同步，也不缓存历史视频帧；它把最近 2 秒内收到的最新检测
结果叠加到当前画面，适合联调消息和绘制效果，不作为逐帧准确性验收工具。关闭 Viewer
只断开预览，不会停止 Worker。

## 检测结果

Worker 对每个推理帧执行：

```text
PUBLISH vision:telemetry:{task_id}
SET vision:task:{task_id}:latest <json> EX 5
```

Redis 只传输检测元数据，不传输原始视频。断线或发布落后时只保留最新待发送结果，不阻塞
推理，也不补发过期帧。消息契约定义在 `src/algorithm/contracts/detection.py`。

## 测试

```bash
uv run pytest
uv run --extra viewer pytest
TEST_DATABASE_URL=postgresql://... uv run pytest \
  tests/integration/test_postgres_task_parameters_integration.py
```

普通单元测试使用假数据库、假进程、假 RTSP 和假 Redis，不依赖摄像头或 GPU。真实
PostgreSQL 与 Redis 集成测试分别通过 `TEST_DATABASE_URL`、`TEST_REDIS_URL` 显式启用。
