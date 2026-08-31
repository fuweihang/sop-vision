# 2026-08-31｜Camera 临时切源与播放器显示模式

## 变化

- Camera Detail 现在把 `status=ONLINE` 且 `whep_url` 非空的 Source 视为可播放源。Backend 默认源
  可播放时优先，否则使用详情响应顺序中的第一路可播放源。
- 操作栏增加 Source Select。选择只影响当前页面预览，不调用默认源 PATCH；临时 Source 在详情刷新后
  仍可播放时保留，删除或不可播放后回到默认源优先规则。
- 停止预览后仍可切换 Source、网页全屏和浏览器全屏，依赖媒体的播放、刷新与音量控件禁用。再次开始
  才 acquire 当前 Source；临时切源会释放旧 Lease 并自动播放新 Stream。
- 增加占满浏览器 viewport 的网页全屏，并与 Fullscreen API 浏览器全屏互斥。切换和退出不会重建
  `VideoSurface`、MediaStream、video DOM 或当前 WHEP Session。
- 标准浏览器验收源改为动态测试图与彩条测试图两路 synthetic RTSP/WHEP 流，便于直接确认切源结果。

## 影响

- Backend API、OpenAPI、数据库、MediaMTX 配置、环境变量和 vendored `reader.js` 无变化。
- 临时 Source、预览意图和显示模式只存在于当前 React 页面状态；不写入 URL、Query cache、
  localStorage、IndexedDB 或 Backend。
- shadcn Select 增加通用 overlay 样式和可选 Portal 容器，使 Source 下拉层在浏览器全屏中仍位于
  `VideoSurface` 内。

## 验证

通过 Source 解析与页面状态测试、Session acquire/release 测试、Select 全屏 Portal 测试、两种全屏
互斥与清理测试，以及 Frontend 静态检查和构建验证。真实浏览器使用 Compose MediaMTX、双路
`pnpm whep:test-source` 和 `VITE_API_MOCK_SCENARIO=whep-player pnpm dev` 验收。

当前规则见 [WHEP 浏览器播放](../modules/cameras/whep-player.md)和
[Camera 详情](../modules/cameras/camera-detail.md)。
