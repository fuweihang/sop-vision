# 07｜WHEP 播放基础与 Camera 详情播放器

> 前置：[Stream Gateway](../../../modules/cameras/stream-gateway.md)、
> [Camera 详情](../../../modules/cameras/camera-detail.md)
>
> 交付：共享 WHEP Session、通用视频表面和 Camera 详情页自定义播放器

## 范围

07 只完成可复用的浏览器播放基础，并把它接入现有 Camera 详情页。播放入口是详情响应中默认
Source 的 `source_id` 和非空 `whep_url`；Frontend 不拼接 WHEP 地址，也不访问 MediaMTX Control
API。

本阶段包含：

- 固定使用 MediaMTX `v1.20.1` 官方 `reader.js`，在项目内保存可审查副本。
- 使用 `WhepSession` 屏蔽 `MediaMTXWebRTCReader`、回调和 `MediaStream` 组装细节。
- 使用 `StreamSessionManager` 按 `source_id` 共享连接并管理引用计数。
- 提供只负责视频、HTML overlay 和媒体 DOM 生命周期的 `VideoSurface`。
- 在 Camera 详情页实现自动开始、开始/停止、静音/音量、全屏、LIVE、连接状态和重连。

本阶段不包含：

- Camera Card、列表视口检测和列表播放器容量控制，这些由 08 负责。
- Detection WebSocket、Canvas、BoxBuffer、检测框坐标转换和帧时间同步，这些跟随 Detection Tasks
  实时数据链路实现。
- 进度条、seek、快进、快退和 DVR。
- `getStats()` 采样、FPS、码率、丢包、Jitter、RTT 和质量面板。

## MediaMTX reader 边界

把 MediaMTX `v1.20.1` 的
`internal/servers/webrtc/reader.js` 原样保存到 `frontend/src/vendor/mediamtx/reader.js`，保留上游
版权信息，并在同目录记录版本、来源 URL 和 SHA-256
`a802f229b803c33713d4c69c4cc0d480108a5bf384947aeee4aaf04268bf85c1`。项目代码不直接修改该文件；
升级 MediaMTX 时必须同时审查和更新 vendored 文件、类型声明与真实播放验收。

`reader.js` 是按固定来源和 SHA-256 管理的第三方源码，不参与 ESLint、Prettier 和 TypeScript 检查。
只把这个精确文件加入 `eslint.config.js` 的全局忽略和 `.prettierignore`，不能忽略整个 `vendor/` 或
`features/video/`。增加 `frontend/scripts/check-mediamtx-reader.mjs` 和对应 pnpm 命令，使用 Node
内置 Crypto 校验本地文件 SHA-256；Adapter、声明文件、Provider、hooks、components 和测试继续执行
项目全部静态检查。`frontend/scripts/**/*.mjs` 继续参与 ESLint 和 Prettier，并在 ESLint 配置中使用
Node globals；不能把项目自有脚本加入忽略列表。

官方 reader 负责 OPTIONS、SDP POST、Trickle ICE、PeerConnection、WHEP Session 和它内置的
断线重试。`WhepSession` 只通过官方构造参数、`onTrack`、`onError` 和 `close()` 工作，不读取其私有
字段。React 组件、Session 共享、播放器状态、HTML UI 和页面生命周期不得写入 vendor 文件。

MediaMTX v1.20.1 官方 `close()` 关闭本地 PeerConnection 和重试定时器，但正常关闭不公开 Session
URL，也不主动发送 WHEP `DELETE`。本阶段保证同一 Source 只有一个活动 PeerConnection，并完整清理
reader、Track、MediaStream、订阅和引用；远端 Session 由连接断开和 MediaMTX 超时回收，不修改官方
文件补充主动删除。

`reader.js` 使用浏览器全局类而不是 ES Module。项目为公开构造参数和 `close()` 补充最小 TypeScript
声明，禁止用 `any` 或让业务组件直接访问 `window.MediaMTXWebRTCReader`。官方版本没有公开
`RTCPeerConnection`，因此本阶段不伪造 `getStats()`；后续质量监控只能在 `WhepSession` 边界内增加
受控能力，并同步审查上游升级或最小补丁，React 组件不得依赖 reader 私有实现。

## WHEP Session 与共享

`WhepSession` 对外提供只读状态快照、当前 `MediaStream`、状态订阅和幂等 `close()`。状态至少区分：

```text
idle → connecting → playing
                    ↘ reconnecting
connecting → failed
idle / connecting / playing / reconnecting / failed → closed
```

- 第一个 `onTrack` 到达时创建或更新同一个 `MediaStream`，音视频 Track 都加入其中。
- `onError` 进入 `reconnecting`；官方 reader 继续执行自身重试。再次收到 Track 后回到 `playing`。
- 主动重连先关闭旧 reader、清理旧 Stream，再创建新 reader，不能同时保留两个 reader 的重试循环。
- codec 检测或首次连接无法进入官方重试时转为 `failed`，由用户主动重连。
- `close()` 后忽略迟到回调，关闭 reader 并停止该 Session 拥有的 Track。
- 错误状态和日志不得包含 WHEP URL query、远端响应正文、Camera 凭据或 RTSP URL。

`StreamSessionManager.acquire(sourceId, whepUrl)` 返回一个可订阅的 Lease；Lease 的 `release()` 必须
幂等。缓存项保存 `WhepSession` 和 `refCount`：

```text
source_id
  └─ WhepSession
      ├─ MediaStream
      └─ refCount
```

- 同一 `source_id` 的并发 acquire 共享一次创建过程和同一个 `MediaStream`。
- 每个消费者拥有自己的 `<video>`；可以独立设置 muted、volume 和全屏。
- 消费者 release 时只清空自己的 `video.srcObject`，不能停止共享 Track。
- 只有最后一个 Lease release 后才关闭 `WhepSession`、停止 Track 并删除缓存项。
- React 重挂载、Effect 清理重复执行、连接仍在创建时 release 都不能产生负引用或遗留 Session。
- 当前部署中同一 `source_id` 的公开 WHEP URL 在页面生命周期内通常稳定。若仍收到同一 Source 的
  新 URL，Manager 必须原子关闭旧 Session、创建一个新 Session 并把新快照通知全部现存 Lease，不能
  在切换窗口保留两条连接。`source_id` 或 `whep_url` 是否为空发生变化时，React hook 先 release 旧
  Lease，再按最新输入决定是否 acquire。

Manager 由应用 Provider 创建，一次页面应用只创建一个实例；测试和应用卸载时统一关闭全部缓存项，
不使用不可重置的模块全局单例。

## VideoSurface 与目录

推荐目录按“媒体基础能力”和“Camera 业务组合”分开：

```text
frontend/src/
├── vendor/mediamtx/
│   ├── reader.js
│   ├── reader.d.ts
│   └── README.md
└── features/
    ├── video/
    │   ├── mediamtx/whep-session.ts
    │   ├── sessions/stream-session-manager.ts
    │   ├── react/stream-session-provider.tsx
    │   ├── react/use-stream-session.ts
    │   ├── components/video-surface.tsx
    │   ├── components/video-controls.tsx
    │   ├── types.ts
    │   └── testing/fakes.ts
    └── cameras/components/camera-detail-player.tsx
```

`VideoSurface` 接收 `MediaStream`、`objectFit` 和 React `children`，内部使用无原生 controls 的
`<video autoPlay muted playsInline controls={false}>`。children 作为 video 上方的组合层，由各业务
组件显式放入自己的 Overlay、Controls 或未来的 Canvas；不增加 `isCard`、`isDetail`、
`showControls`、`showBoxes` 等模式布尔值。

`VideoSurface` 可以通过受控 Context 向 children 暴露 video 元素、视频原始宽高、容器宽高和根据
`object-fit` 算出的实际媒体渲染区域。Context 只提供通用媒体状态与操作，不包含 Camera、Card、
Detail、Detection 或 Box 等业务类型。它负责设置和清空 `srcObject`、调用 `play()`、报告自动播放
失败，以及在尺寸变化时更新通用测量值；不读取 Camera DTO，也不创建 WHEP Session。

07 不为尚无数据来源的检测结果创建空 Canvas 或通用帧回调 API。Detection 阶段从 video feature
读取 Context，并把自己的 `BoxCanvas` 作为 child 组合到 `VideoSurface` 内；video feature 不依赖
Detection。每个 Card/Detail 仍使用各自的 video 和 canvas DOM。

## Camera 详情行为

- 默认 Source 的 `whep_url` 非空时自动 acquire；页面现有按钮改为“停止预览”。用户停止后按钮改为
  “开始预览”，不会因为 15 秒详情刷新自动恢复。
- `whep_url=null` 时不 acquire，预览区显示“当前视频源不可播放”和对应 Source 状态，开始按钮禁用；
  后续详情刷新得到非空 URL 时，仅在用户没有主动停止过的情况下自动开始。
- `connecting/reconnecting/playing/failed/stopped` 使用文字和图标表达，不能只依赖颜色。只有实际播放
  时显示 LIVE。
- `reconnecting` 和 `failed` 时提供“重新连接”；点击后调用 Session 的主动重连，不调用 Camera 配置
  写 API。
- 默认静音以满足自动播放限制；用户手势后可以静音、调节音量。没有音频 Track 时隐藏音量操作。
- 浏览器支持时对整个 `VideoSurface` 容器请求全屏，使自定义 controls 和 overlay 保持可见；能力
  不可用时不显示全屏操作，调用失败时在播放器区域内给出可恢复提示。
- 页面隐藏时 release Session；恢复可见时，仅当隐藏前处于用户期望的播放状态才重新 acquire。
- 切换 Source、详情数据返回新的播放入口、路由离开和组件卸载都 release 旧 Lease。

## 实施顺序

1. 保存官方 reader、副本说明与最小 TypeScript 声明；增加精确 lint/format 忽略和 SHA-256 门禁。
2. 实现 `WhepSession`、状态快照及 Fake，覆盖 Track 组装、官方重试回调、主动重连和幂等关闭。
3. 实现 `StreamSessionManager`、Provider 和 hook，覆盖并发 acquire、引用计数及 React 重挂载。
4. 实现 `VideoSurface`、受控 Context 和自定义 controls，覆盖 children 组合、测量、`srcObject`、
   自动播放、音量、全屏与清理。
5. 接入 Camera 详情预览区和开始/停止按钮，补齐离线、连接、失败、隐藏、恢复及卸载测试。
6. 更新 Cameras 当前能力文档和变更记录，再执行全部 Frontend 与安全门禁。

## 验收

- 同一 `source_id` 的两个测试消费者只有一个 reader 和一个 `MediaStream`，但各自拥有 video DOM；
  释放一个消费者不停止另一消费者，最后释放才关闭 Session。
- 详情在线时默认播放，用户可以停止、再次开始和主动重连；15 秒数据刷新不重复建连。
- `whep_url=null`、自动播放被拒绝、WHEP 失败、页面隐藏/恢复、路由离开和组件卸载都有确定行为。
- `srcObject`、Track、reader 重试循环、Provider 缓存和事件订阅完成清理；React Strict Mode 下不泄漏。
- 音量和全屏按浏览器能力工作，键盘焦点、可访问名称和状态文字符合现有 Design System。
- 浏览器到 MediaMTX 的真实 WHEP 播放使用锁定版本验证；WHEP、日志和缓存不含 RTSP 凭据。

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

## 标准浏览器集成验收

Frontend 使用已固定在 devDependencies 的 `ffmpeg-static@5.3.0`。该包的安装脚本下载当前平台的
FFmpeg 二进制，因此 `frontend/pnpm-workspace.yaml` 只为 `ffmpeg-static` 和既有 `msw` 开放
`allowBuilds`；它不能进入生产 dependencies，也不能被 `frontend/src/` 或 Vite 应用代码导入。

07 增加 `frontend/scripts/run-whep-test-source.mjs` 和 `pnpm whep:test-source`。Node 脚本读取
`ffmpeg-static` 导出的本机可执行文件绝对路径，路径为空时报告当前平台不支持；使用
`child_process.spawn()` 参数数组启动进程，不拼接 shell 命令。脚本前台运行 `lavfi` 合成的
1280×720、30 FPS 测试画面和正弦音频，并通过 RTSP/TCP 发布到 Compose MediaMTX 的固定
`whep-test` Path。视频固定使用 H.264 baseline、`yuv420p`、无 B-frame 和 1 秒 GOP，音频使用
G.711 PCMU；子进程启动或推流失败时脚本返回非零，收到 Ctrl+C/SIGTERM 时转发信号并等待 FFmpeg
退出，不在后台遗留进程。

Node 脚本向 FFmpeg 传入以下等价参数，不下载媒体文件，也不使用 Camera Fixture 中的 RTSP 地址：

```bash
# 此处 ffmpeg 表示 ffmpeg-static 导出的绝对路径，不从 PATH 查找。
ffmpeg -hide_banner -loglevel info \
  -re -f lavfi -i testsrc2=size=1280x720:rate=30 \
  -re -f lavfi -i sine=frequency=1000:sample_rate=8000 \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -profile:v baseline -level:v 3.1 \
  -preset veryfast -tune zerolatency -pix_fmt yuv420p \
  -g 30 -keyint_min 30 -sc_threshold 0 -bf 0 \
  -c:a pcm_mulaw -ar 8000 -ac 1 \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/whep-test
```

Frontend 增加显式的 `whep-player` MSW 开发场景，只把固定 Camera Fixture 默认 Source 的
`whep_url` 改为 `http://127.0.0.1:8889/whep-test/whep`。REST 继续由 MSW 提供，WHEP 请求不能被 MSW
拦截。Browser Mock 只在该场景下放行 `http://127.0.0.1:8889/whep-test/whep` 及其 Session 子路径，
用于 OPTIONS、POST、PATCH 和 MediaMTX 返回的 Session URL；其他未处理请求继续报错，不能按端口或
全部跨域请求宽泛放行。标准步骤为：

```bash
# 终端一：启动锁定版本 MediaMTX
docker compose up -d mediamtx

# 终端二：前台启动合成 RTSP Source
cd frontend
pnpm whep:test-source

# 终端三：启动固定详情场景
cd frontend
VITE_API_MOCK_SCENARIO=whep-player pnpm dev
```

在支持的 Chrome 中打开
`http://127.0.0.1:8000/cameras/6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21`，验证自动播放、停止/开始、
主动重连、音量、全屏、隐藏/恢复和路由离开。Network 面板中同一时刻只能有该 Source 的一个活动
PeerConnection；浏览器 console 和测试记录不得出现 Camera 凭据或完整 RTSP URL。自动测试仍使用
Fake 隔离 WebRTC。真实 IPC/RTSP 设备、更多 Codec、NAT 和容量组合继续由 11 发布门禁验收。
