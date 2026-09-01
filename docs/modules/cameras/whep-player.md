# WHEP 浏览器播放

> 相关文档：[Camera 详情](camera-detail.md)、[Stream Gateway](stream-gateway.md)、
> [MediaMTX 契约](mediamtx-contract.md)

## 当前能力

Frontend 使用 MediaMTX WHEP/WebRTC 播放 Camera 当前选中的可播放 Source。详情响应提供
`source_id` 和 `whep_url`；浏览器不拼接地址，也不访问 MediaMTX Control API。

```text
MediaMTX reader.js → WhepSession → StreamSessionManager → MediaStream
                                                        ├→ Detail VideoSurface
                                                        └→ Card VideoSurface
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
  用户在首帧前暂停，或暂停后刷新并收到新 Stream 时，Badge 显示“等待画面”且不显示 loading、
  不计算首帧超时；继续播放后恢复首帧等待和超时计时。
  `LIVE` 也只在当前 video 已渲染首帧后显示。播放状态下等待首帧超过 `10s` 时，Badge 显示“画面超时”
  并提供刷新提示。WHEP Session 连接失败时，运行中的预览在常驻错误提示中直接提供“刷新当前流”；
  停止预览后不显示旧媒体错误或恢复按钮。网页全屏让同一个 VideoSurface 占满浏览器 viewport
  并锁定页面滚动；浏览器全屏使用 Fullscreen API。两种模式互斥，切换时不重建 Session、Stream 或
  video DOM。状态和 LIVE 同时使用文字表达。
- WHEP 是实时流，不提供进度、seek、快进、快退或 DVR。

## Camera Card 行为

- Card 只使用列表摘要中的默认 `source_id+whep_url`，不请求 CameraDetail、不选择备用 Source，也不
  修改 Backend 默认源。
- `whep_url` 非空的 Card 挂载时 acquire，并以 `cover`、自动播放、静音和无 controls 的方式展示；
  连接、重连和等待当前 video 首帧期间在媒体区中央显示 loading。左上角显示 Session 与当前 video
  出画结果组合后的状态，不显示 Backend Source 状态；首帧前显示“正在加载”，出画后才显示 `LIVE`，
  等待超过 `10s` 显示“画面超时”。
- Lease 生命周期不读取视口相交比例或 Page Visibility。滚动离开视口和页面 hidden 都保持连接；
  搜索或翻页替换 Card、离开路由、组件卸载、URL 变化或变为 `null` 时释放旧 Lease。
- Card 与 Detail 命中相同 `source_id+whep_url` 时复用一个 reader 和 MediaStream，各自拥有独立 video；
  每个 video 独立确认首帧，只有最后一个消费者 release 才关闭 Session、停止 Track 并清空关联的
  `srcObject`。
- `whep_url=null` 时不 acquire、也不渲染 video，只显示 Source 名称和“不可预览”。

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

Chrome 打开 `http://127.0.0.1:8000/cameras` 或
`http://127.0.0.1:8000/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21`。`whep-player` MSW
场景只放行以下两个固定入口及各自的 Session 子路径，其他未处理请求继续报错：

- `http://127.0.0.1:8889/whep-test-primary/whep`
- `http://127.0.0.1:8889/whep-test-secondary/whep`

## 当前边界与排查

- 一页多路容量上限尚未经过真实部署发布验收；当前 UI 首屏默认最多展示 12 路，Card 不按视口或
  页面 hidden 状态暂停连接。
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
