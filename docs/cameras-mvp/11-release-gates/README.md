# 11｜Cameras MVP 发布门禁

> 前置：02–10 全部切片
>
> 交付：真实依赖、端到端故障、安全、浏览器和容量验收；无新公共路由

本切片不实现缺失业务能力，只验证前序切片组合后仍满足根契约。发现失败必须回到对应事实所有者
修复，不能在此增加第二份业务规则或临时兼容分支。

## 契约与静态门禁

- 锁定的 MediaMTX 版本、受控 OpenAPI、Adapter Fixture 和运行镜像完全一致。
- Router、Backend Schema、`contracts/openapi.json`、Frontend 类型、Client、MSW 与 Fixture 无
  漂移；Playback 只暴露 `POST prepareCameraSourcePlayback`，没有含义重叠的安全读取操作。
- 七个公共 handler 都有真实 Application Service 和依赖装配，零占位。
- Markdown 相对链接、切片状态、Path 命名和公共规则没有重复事实源。

## Desired/Runtime State 故障

- MediaMTX 停机期间 Camera 创建、详情、列表、更新、默认源和删除仍遵守各自数据库契约。
- MTX 重启清空内存配置后，Reconciler 在约定窗口恢复全部数据库 Source Path。
- 即时同步部分成功、进程在数据库提交后崩溃、周期对账单项失败都能在后续轮次收敛。
- 缺失、漂移和孤儿 Path 修复准确，不删除非受管 Path，不记录远端完整配置。
- Backend 多 worker/实例只有一个活动 Reconciler；Playback、更新、删除交错后最终状态等于数据库。
- Playback 能恢复用户正在访问的单 Source，但未访问 Source 的恢复不依赖 Playback。

## 播放与浏览器

- 在线 Camera Card 直接使用列表 `whep_url`，正常一页只有列表 REST 请求和 WHEP 媒体请求，没有
  逐 Card Playback REST N+1。
- 只有 Path 缺失或一次 WHEP 协商恢复才调用 Playback；离线/MTX 故障不会触发请求风暴。
- 覆盖支持的 Camera Codec、浏览器范围、HTTPS、ICE additional hosts、局域网/NAT 可达性和
  `PUBLIC_WEBRTC_BASE_URL` 带路径前缀的 URL 连接。
- 离开视口、隐藏页面、切页、切源、删除和卸载均关闭 PeerConnection、停止轨道并清空
  `srcObject`。
- 容量基线至少覆盖一页 20 个 Camera、多路 Source 配置和同时可见 Card 会话；资源上限与失败
  文案必须通过真实部署验证，不能只依赖 jsdom。

## 安全与数据边界

- RTSP 凭据中的 URI 保留字符正确编码，MediaMTX 能连接且日志不回显明文。
- CameraDetail 之外的列表、Playback、Problem、日志、指标、追踪和错误上报不存在用户名、密码、
  后缀或完整 RTSP URL。
- Control API 不暴露给浏览器网络；WHEP 使用部署要求的 HTTPS 与来源限制。
- CameraDetail 和 PlaybackInfo 不进入浏览器持久化存储；播放器释放后不保留媒体对象。
- 当前无鉴权、字段加密和 Secret 管理的风险继续作为发布网络边界，不因媒体门禁通过而消失。

## 验证命令

```bash
# 仓库根目录
docker compose config
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# backend/
uv run --env-file .env.local pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_camera_placeholders.py mvp

# frontend/
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

PostgreSQL 集成测试必须使用独立 `TEST_DATABASE_URL`；MediaMTX Adapter 和端到端测试必须使用
锁定版本的隔离实例。依赖未配置导致的跳过不能算作发布验收通过。
