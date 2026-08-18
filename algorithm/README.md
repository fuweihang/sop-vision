# SOP Vision Algorithm

`algorithm` 是 SOP Vision 的算法服务。守护进程通过本地 `config.json`
管理独立 AIWorker；外部平台只发送启动、重载、重启和停止命令，不传递算法参数。
Detector 从 RTSP 拉流、在 GPU 上执行 YOLO，并将检测元数据直接写入 Redis，整个
Worker 不创建 OpenCV 窗口。

## 架构

```text
运维人员 ──修改──> config.json
                      │
平台 FastAPI ──HTTP──> Algorithm Daemon ──spawn/Event/Pipe──> AIWorker
                                                          │
平台 FastAPI <────────────────── Redis <────检测结果───────┘
```

- 守护进程只提供控制面，不转发检测结果。
- Worker 直接发布实时结果和最近一帧快照。
- ROI 是本地配置的一部分，修改后通过 `reload` 完整重启 Worker 生效。
- 守护进程启动后不会自动启动任何 Worker，也不会持久化运行状态。

## 安装

要求 Python 3.12，推荐使用 `uv`：

```bash
uv sync --dev
cp config.example.json config.json
```

`config.json` 包含视频源凭据，已被 `.gitignore` 排除。生产环境建议将文件权限设置为
仅算法服务用户可读。相对模型路径以配置文件所在目录为基准。

配置示例：

```json
{
  "schema_version": 1,
  "workers": {
    "detector-001": {
      "type": "detector",
      "config": {
        "camera_id": "camera-001",
        "source_id": "source-001",
        "rtsp_url": "rtsp://user:password@camera/stream",
        "redis_url": "redis://127.0.0.1:63793/0",
        "model_path": "resources/models/yolo26n.pt",
        "image_size": 640,
        "confidence": 0.5,
        "device": "0",
        "reconnect_delay_seconds": 2.0,
        "algorithm_id": "yolo_object_detection",
        "algorithm_version": "0.1.0",
        "roi": {
          "roi_id": "main",
          "points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        }
      }
    }
  }
}
```

`workers` 的 key 就是 `task_id`。将 `roi` 设置为 `null` 可执行全画面检测。
ROI 坐标归一化到 `[0, 1]`，至少需要三个不重复且能组成非零面积多边形的点。

更新配置时应先写临时文件，再在同一文件系统内原子重命名为 `config.json`，避免守护
进程读取到半写入内容。

## 启动与控制

启动守护进程：

```bash
uv run algorithm-daemon
```

默认监听 `0.0.0.0:8090`，默认读取当前目录的 `config.json`。可以覆盖：

```bash
ALGORITHM_CONFIG_PATH=/etc/sop-vision/config.json \
uv run algorithm-daemon --host 127.0.0.1 --port 8090
```

第一版没有应用层鉴权，必须部署在可信网络并通过防火墙限制访问。

控制指定任务，请发送空请求体：

```bash
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/start
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/reload
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/restart
curl -X POST http://127.0.0.1:8090/v1/workers/detector-001/stop
curl http://127.0.0.1:8090/healthz
```

命令语义：

- `start`：重新读取配置；任务未运行时按磁盘配置启动，已运行时幂等成功。
- `reload`：先停止任务，再读取配置并使用新参数启动；配置无效时保持停止。
- `restart`：不读取磁盘，使用最后一次成功加载到内存的配置重新启动。
- `stop`：只停止 Worker，守护进程继续运行，并保留内存配置以供 `restart` 使用。

命令同步等待模型加载和 Worker 主循环就绪。RTSP 或 Redis 暂时断开不会影响启动成功，
对应组件会在后台持续重连。Worker 意外退出后不会自动重启。

也可以绕过守护进程调试单个任务：

```bash
uv run detector --config config.json --task-id detector-001
```

## 检测结果

每个完成推理的帧都会生成 `frame_detection`。没有目标时也发送空 `objects`：

```json
{
  "schema_version": 1,
  "type": "frame_detection",
  "task_id": "detector-001",
  "camera_id": "camera-001",
  "source_id": "source-001",
  "algorithm_id": "yolo_object_detection",
  "algorithm_version": "0.1.0",
  "run_id": "54a81572-94a1-4bd5-a39f-f4ff06ef587a",
  "frame_id": 18272,
  "frame_ts_ms": 1786501200123,
  "published_at_ms": 1786501200180,
  "source_width": 1920,
  "source_height": 1080,
  "roi_id": "main",
  "objects": [
    {
      "class_id": 0,
      "class_name": "person",
      "confidence": 0.96,
      "bbox": [0.21, 0.11, 0.48, 0.91],
      "attributes": {}
    }
  ],
  "metrics": {"inference_ms": 18.4, "fps": 24.7}
}
```

Worker 同时执行：

```text
PUBLISH vision:telemetry:{task_id}
SET vision:task:{task_id}:latest <json> EX 5
```

Redis 断线或发布速度落后于推理时，只保留最新待发送结果，不阻塞推理，也不补发过期帧。
Redis 仅传输检测元数据，不传输原始视频帧、JPEG 或视频流。

## 测试

```bash
uv run pytest
```

单元测试使用假 Worker、假 RTSP 和假 Redis，不依赖真实摄像头或 GPU。
