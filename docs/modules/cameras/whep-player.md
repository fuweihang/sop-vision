# WHEP 浏览器播放

> 相关文档：[Camera 详情](camera-detail.md)、[Stream Gateway](stream-gateway.md)、
> [MediaMTX 契约](mediamtx-contract.md)

## 当前能力

Frontend 使用 MediaMTX WHEP/WebRTC 播放 Camera 当前选中的可播放 Source。详情响应提供
`source_id` 和 `whep_url`；浏览器不拼接地址，也不访问 MediaMTX Control API。

```text
MediaMTX reader.js → WhepSession → StreamSessionManager → MediaStream
                                                        └→ Detail VideoSurface
```

- `frontend/src/vendor/mediamtx/reader.js` 是 MediaMTX `v1.20.1` 官方文件的原样副本。项目通过
  `pnpm vendor:check` 校验固定 SHA-256；只有该文件不参与 ESLint、Prettier 和 TypeScript 检查。
  应用启动和普通页面不会加载它，第一次创建 WHEP Session 时才通过动态 import 执行。
- `WhepSession` 组装音视频 Track，向 React 提供 `connecting/playing/reconnecting/failed/closed`
  快照，并在主动重连和关闭时停止旧 Track。上游原始错误不会进入 UI 或日志。
- `StreamSessionManager` 按 `source_id` 缓存 Session 并管理引用计数。同一路流的消费者共享
  `MediaStream`，但各自拥有 `<video>`；最后一个 Lease 释放后才关闭 Session。
- `VideoSurface` 只接收 `MediaStream`、`cover/contain` 和 React children。受控 Context 提供 video
  元素、源尺寸、容器尺寸、实际媒体区域、音频和全屏等通用能力，不包含 Camera 或 Detection 类型。

## Camera 详情行为

- Frontend 先确认 `default_preview_source_id` 能匹配实际 Source；匹配失败显示损坏响应错误，不用其他
  Source 掩盖问题。`status=ONLINE` 且 `whep_url` 非空才可播放。
- 未临时切源时优先选择可播放的 Backend 默认源；默认源不可播放时使用响应顺序中的第一路可播放源。
  全部 Source 不可播放时不 acquire，显示“当前视频源不可播放”并禁用开始按钮。
- Source Select 列出全部 Source，不可播放项保持可见但禁用。用户选择只保存在当前 Detail 页面内存，
  不发送默认源 PATCH，也不写入 URL、Query cache 或浏览器持久化存储。
- 临时 Source 在 15 秒详情刷新后仍可播放时继续使用；被删除、离线或失去 WHEP URL 后 release 旧
  Lease，并重新执行默认源优先规则。切换可播放 Source 会自动播放新 Stream。
- 用户停止后，详情刷新、Backend 默认源变化和 Source 可用性变化都不会自行恢复预览。停止状态仍可
  切换 Source 和显示模式，播放、刷新与音量控件禁用；再次开始后连接当前已解析的 Source。
- 页面隐藏时保持 Lease；用户停止、路由离开、Source 改变和组件卸载时 release。
- 播放器默认静音且音量为 `0`，用户可通过音量按钮取消静音；浏览器拒绝播放请求时显示继续播放
  提示。首次取消静音使用 `70%` 音量。通过音量按钮静音时，音量和滑块同时归零，再次点击时恢复
  静音前的音量；通过 Slider 调到 `0%` 时，再次取消静音恢复到 `70%`。音量按钮在连接和重连期间
  常驻；音量浮层仅在鼠标 hover 时显示，点击音量按钮不改变浮层可见性。
  刷新后恢复刷新前的播放/暂停状态。首次连接和重连时显示 loading，收到当前 Stream 首帧后结束；
  播放状态下等待首帧超过 `10s` 时显示刷新提示。网页全屏让同一个 VideoSurface 占满浏览器 viewport
  并锁定页面滚动；浏览器全屏使用 Fullscreen API。两种模式互斥，切换时不重建 Session、Stream 或
  video DOM。状态和 LIVE 同时使用文字表达。
- WHEP 是实时流，不提供进度、seek、快进、快退或 DVR。

## 开发验收源

`ffmpeg-static@5.3.0` 是 Frontend 的精确 devDependency，`pnpm whep:test-source` 使用它同时生成
H.264 baseline + G.711 PCMU 的 1280×720、30 FPS 动态测试图和彩条测试图。进程在前台运行，
Ctrl+C/SIGTERM 会转发给 FFmpeg，不会留下后台进程。

```bash
# 终端一：仓库根目录
docker compose up -d mediamtx

# 终端二：frontend/
pnpm whep:test-source

# 终端三：frontend/
VITE_API_MOCK_SCENARIO=whep-player pnpm dev
```

Chrome 打开
`http://127.0.0.1:8000/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21`。`whep-player` MSW
场景只放行以下两个固定入口及各自的 Session 子路径，其他未处理请求继续报错：

- `http://127.0.0.1:8889/whep-test-primary/whep`
- `http://127.0.0.1:8889/whep-test-secondary/whep`

## 当前边界与排查

- Camera Card 播放、视口检测和一页多路容量控制尚未实现。
- Detection Canvas、BoxBuffer、时间戳同步和 WebRTC Stats 尚未实现。
- 当前音量浮层只能由指针 hover 打开，键盘无法直接访问其中的 Slider；这是已知可访问性限制，
  发布前必须按 Cameras 发布门禁修复和验收。
- 真实 IPC、更多 Codec、HTTPS、ICE additional hosts、NAT 和容量组合在 Cameras 发布门禁验证。
- 页面一直停在“正在连接”时，先确认 synthetic source 正在向
  `rtsp://127.0.0.1:8554/whep-test-primary` 和 `whep-test-secondary` 推流，再检查浏览器能否访问
  `127.0.0.1:8889` 和 `8189/udp`。
- 生产部署必须让 `PUBLIC_WEBRTC_BASE_URL` 和 `MTX_WEBRTCADDITIONALHOSTS` 对浏览器可达，并使用
  TLS 与合适的来源限制。

## 验证命令

```bash
# 仓库根目录
bash scripts/check-cameras-sensitive-data.sh

# frontend/
pnpm vendor:check
pnpm test
pnpm lint
pnpm format:check
pnpm build
```
