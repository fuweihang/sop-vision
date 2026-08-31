# 2026-08-30｜Camera WHEP 详情播放器

## 变化

- Frontend 使用 MediaMTX v1.20.1 官方 `reader.js` 接入 WHEP/WebRTC，并通过固定来源和 SHA-256
  校验 vendored 文件；官方脚本只在第一次创建 WHEP Session 时动态加载，不进入应用主入口 chunk。
- 增加按 `source_id` 引用计数的共享 Session Manager、通用 `VideoSurface` children/Context 接口和
  Camera 详情自定义播放器。
- `video-surface`、`video-controls` 和 `stream-session` 分别提供公共入口，内部 Context、hooks 和测试
  与对应实现放在同一目录；通用 Session 类型不使用 WHEP 专用命名。
- 详情默认自动预览，支持开始/停止、静音/音量、全屏、LIVE、连接状态和主动重连；播放会话按用户
  的预览意图保持，页面隐藏时不主动断开，停止预览或卸载时释放 Lease。
- 播放器默认静音且音量为 `0`，首次取消静音使用 `70%`；音量按钮静音后恢复静音前音量，Slider
  归零后恢复 `70%`。刷新时保留刷新前的播放/暂停状态，连接和重连期间显示 loading，视频首帧出现
  后结束，等待首帧超过 `10s` 时提供刷新入口；音量按钮保持显示。
- 增加 `ffmpeg-static` synthetic RTSP 源与 `whep-player` MSW 场景，用于不依赖真实 Camera 的浏览器
  集成验收。

## 影响

- Backend API、OpenAPI、数据库和环境变量无变化；Frontend 直接使用详情响应已有的 `whep_url`。
- 新增精确 devDependency `ffmpeg-static@5.3.0`。安装会下载当前平台 FFmpeg，但它不会进入最终 nginx
  镜像或浏览器产物。
- `reader.js` 不参与项目格式化和静态检查；动态加载包装器、Adapter、Session、React、脚本和测试仍
  执行全部门禁。
- 当前不包含 Camera Card、Detection Canvas、WebRTC Stats、DVR 或真实 IPC 兼容性保证。

## 验证

使用 Session/Manager/VideoSurface/Camera 页面单元测试、vendored 文件 SHA-256 校验、Frontend 静态
检查与构建验证。标准浏览器验收使用 Compose MediaMTX、`pnpm whep:test-source` 和
`VITE_API_MOCK_SCENARIO=whep-player pnpm dev`。

当前规则见 [WHEP 浏览器播放](../modules/cameras/whep-player.md)。
