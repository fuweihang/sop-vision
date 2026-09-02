# 11｜Cameras MVP 发布门禁

> 前置：[Cameras 当前能力](../../../modules/cameras/README.md)与 09–10 全部任务
>
> 交付：真实依赖、端到端故障、安全、浏览器和容量验收；无新公共路由

本切片不实现缺失业务能力，只验证前序切片组合后仍满足根契约。发现失败必须回到对应事实所有者
修复，不能在此增加第二份业务规则或临时兼容分支。

## 契约与静态门禁

- 锁定的 MediaMTX 版本、受控 OpenAPI、vendored `reader.js`、Adapter Fixture、真实 Adapter 门禁和
  运行镜像完全一致。
- Router、Backend Schema、`contracts/openapi.json`、Frontend 类型、Client、MSW 与 Fixture 无漂移。
- 六个公共 handler 都有真实 Application Service 和依赖装配，零占位。
- Markdown 相对链接、切片状态、Path 命名和公共规则没有重复事实源。

## Desired/Runtime State 故障

- MediaMTX 停机期间 Camera 创建、详情、列表、更新、默认源和删除仍遵守各自数据库契约。
- MTX 重启清空内存配置后，Reconciler 在约定窗口恢复全部数据库 Source Path。
- 即时同步部分成功、进程在数据库提交后崩溃、周期对账单项失败都能在后续轮次收敛。
- 缺失、漂移和孤儿 Path 修复准确，不删除非受管 Path，不记录远端完整配置。
- Backend 多 worker/实例只有一个活动 Reconciler；更新、删除交错后最终状态等于数据库。

## 播放与浏览器

- 在线 Camera Card 直接使用列表 `whep_url`，正常一页只有列表 REST 请求和按已挂载 Source 去重后的
  WHEP 媒体请求。
- 覆盖支持的 Camera Codec、浏览器范围、HTTPS、ICE additional hosts、局域网/NAT 可达性和
  `PUBLIC_WEBRTC_BASE_URL` 带路径前缀的 URL 连接。
- Card 与 Detail 同时消费一路 Source 时只有一个 reader 和 MediaStream，各自使用独立 video DOM；
  单个消费者 release 不停止共享 Track，最后一个消费者 release 后清空 Session 缓存和全部
  `srcObject`。
- Detail 按用户的开始/停止预览意图持有 Lease；已挂载且有 `whep_url` 的 Card 持有 Lease。页面隐藏和
  Card 离开视口都保持连接；搜索或翻页替换 Card、切源、删除、路由离开和卸载会 release 对应 Lease，
  React Strict Mode 重挂载不重复建连或产生负引用。
- 详情页的开始/停止预览与 video 播放/暂停独立；暂停保留当前帧和 Lease，继续直接进入实时
  画面，不影响共享 MediaStream 的其他消费者。
- 贴底全宽渐变操作栏的鼠标活动/自动隐藏、触摸、音量浮层、刷新、首帧渲染后才显示的 LIVE 和连接状态通过
  支持浏览器验收；音量浮层可用键盘打开和关闭，Slider 可用键盘调整，焦点始终可见且关闭后正确
  返回触发按钮。Card 保持静音且不显示 Detail controls。
- 至少一路 Source 可播放时，Detail 不读取 Backend 默认源，按响应顺序选择第一路可播放 Source；
  全部 Source 不可播放时不创建 Session，并沿用不可播放展示。默认源只控制 Camera Card。
- 临时 Source 切换只影响当次 Detail 预览，不发送默认源 PATCH；旧 Lease 释放、新 Lease acquire、
  Source 删除或不可播放后回退、网页全屏与浏览器全屏互斥/退出、模式切换不重建 Session 均通过验收。
- 标准浏览器验收使用两路视觉可区分的 synthetic RTSP/WHEP 流，验证 Detail 按排序自动选择、临时
  Source 失效后按排序回退、Card 跟随默认源，以及两个 Path 各自 Session 的 acquire/release。
- Frontend 的 FFmpeg synthetic RTSP Source 只验证可重复的基础播放与浏览器生命周期；发布验收必须另外
  使用目标 IPC/RTSP 设备覆盖支持的 Codec、厂商实现和长时间连接，不能用合成源代替。
- 容量基线至少覆盖一页 20 个 Camera、多路 Source 配置和全部已挂载 Card 会话；资源上限与失败
  文案必须通过真实部署验证，不能只依赖 jsdom。

## 安全与数据边界

- RTSP 凭据中的 URI 保留字符正确编码，MediaMTX 能连接且日志不回显明文。
- CameraDetail 之外的列表、Problem、结构化日志、追踪和错误上报不存在用户名、密码、
  后缀或完整 RTSP URL。
- Control API 不暴露给浏览器网络；WHEP 使用部署要求的 HTTPS 与来源限制。
- CameraDetail 不进入浏览器持久化存储；最后一个播放器 Lease 释放后不保留媒体对象。
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
uv run python scripts/check_mediamtx_contract.py
uv run python scripts/check_mediamtx_adapter.py
uv run python scripts/check_camera_placeholders.py mvp

# frontend/
pnpm vendor:check
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

PostgreSQL 集成测试必须使用独立 `TEST_DATABASE_URL`；MediaMTX 契约、Adapter 和端到端测试必须
使用锁定版本的隔离实例。依赖未配置导致的跳过不能算作发布验收通过。
