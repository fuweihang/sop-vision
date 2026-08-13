# SOP Vision Algorithm

`algorithm` 是 SOP Vision 的算法服务层。每个 AI Worker 都是独立进程；模型推理、ROI、RTSP 和消息通信等能力按职责拆分，供多个 Worker 复用。

当前包含一个轻量 `detector` demo：从 IP Camera 拉取 RTSP，使用预训练 `YOLO26n` 进行整帧目标检测，通过 Redis Pub/Sub 实时更新多边形 ROI，并使用 OpenCV 窗口展示状态。

## 目录结构

```text
algorithm/
├── resources/
│   ├── models/                  # 下载的模型权重，不提交 Git
│   └── samples/                 # 示例 ROI，后续可放测试媒体
├── src/algorithm/
│   ├── algorithms/
│   │   └── object_detection/    # 可复用的 YOLO 推理封装
│   ├── common/                  # 配置、ROI、RTSP、Redis 基础设施
│   ├── workers/
│   │   └── detector/            # 独立 detector 进程
│   └── tools/                   # ROI 发布等运维命令
└── tests/
    ├── unit/
    └── integration/
```

新增 Worker 时，在 `workers/<worker_name>` 编排进程生命周期；不要把可复用的模型逻辑或 Redis/视频客户端复制到 Worker 内。

## 安装与启动

要求 Python 3.12，并推荐使用 `uv`：

```bash
uv sync --dev
uv run detector
```

默认配置：

| 配置 | 默认值 |
| --- | --- |
| 模型 | `resources/models/yolo26n.pt` |
| Redis | `redis://127.0.0.1:63793/0` |
| Task ID | `detector-demo` |
| ROI channel | `vision:config:roi:detector-demo` |
| 输入尺寸 | `640` |
| 置信度 | `0.25` |
| 计算设备 | 第一张 NVIDIA GPU（`0`） |

代码中按 demo 要求提供了指定摄像头的默认 RTSP 地址。日志会隐藏 URL 中的用户名和密码。正式环境应使用环境变量或 Secret 覆盖，避免长期在代码中保留凭证：

```bash
DETECTOR_RTSP_URL='rtsp://user:password@camera/stream' \
DETECTOR_REDIS_URL='redis://127.0.0.1:63793/0' \
uv run detector
```

所有配置也可以用命令行覆盖：

```bash
uv run detector \
  --rtsp-url 'rtsp://user:password@camera/stream' \
  --redis-url redis://127.0.0.1:63793/0 \
  --task-id detector-demo \
  --confidence 0.25 \
  --device 0
```

程序默认将 YOLO 推理固定到第一张 NVIDIA GPU；也可以用
`DETECTOR_DEVICE=1` / `--device 1` 选择其他显卡。只有明确传入
`--device auto` 时才交给 Ultralytics 自动选择，传入 `--device cpu` 则强制使用 CPU。

启动前可以确认 PyTorch 是否能访问 CUDA：

```bash
uv run python -c 'import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no CUDA device")'
```

执行 `uv run detector --help` 查看完整参数。按 `q`、`Esc` 或发送 `SIGINT`/`SIGTERM` 可退出。

首次启动时 Ultralytics 会下载官方 `yolo26n.pt` 到 `resources/models/`。如果运行环境不能访问模型源，需要提前把同名权重放到该目录。

## 发布 ROI

ROI 使用归一化坐标，不依赖摄像头分辨率。至少提供三个多边形顶点；只有 bbox 中心点位于多边形内部或边界上的目标才会显示。

使用示例文件发布：

```bash
uv run publish-roi --file resources/samples/roi.json
```

直接传 JSON：

```bash
uv run publish-roi --json '{
  "schema_version": 1,
  "type": "roi_update",
  "task_id": "detector-demo",
  "roi_id": "main",
  "enabled": true,
  "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
}'
```

清除 ROI、恢复全画面检测：

```bash
uv run publish-roi --json '{
  "schema_version": 1,
  "type": "roi_update",
  "task_id": "detector-demo",
  "roi_id": "main",
  "enabled": false,
  "points": []
}'
```

非法 JSON、未知字段、task 不匹配、越界坐标、少于三个点或零面积多边形都会被拒绝。Detector 只用合法消息替换当前 ROI。

## 运行语义

- RTSP 解码在线程中持续进行，只保留最新一帧，避免推理较慢时产生无限积压。
- RTSP 或 Redis 断开后按固定间隔自动重连；Redis 故障不会停止视频推理。
- ROI 仅使用 Redis Pub/Sub，不持久化。Detector 离线期间发布的消息无法补发；每次进程启动默认使用全画面，需重新发布 ROI。
- OpenCV `imshow` 要求桌面会话；无显示服务器的容器或远程终端不能运行当前可视化版本。

## 测试

```bash
uv run pytest
```

单元测试不连接真实摄像头或 Redis。真实联调前可先确认 Redis 端口：

```bash
redis-cli -p 63793 PING
```
