# 2026-09-01｜视频展示状态与恢复入口

## 变化

- Camera Detail 的 WHEP Session 连接失败时，常驻错误提示现在直接提供“刷新当前流”按钮，调用现有
  Session 重连能力。
- 操作栏明确区分可操作、只读和停止三种状态。可操作状态按错误类型显示继续播放或刷新；只读状态只
  显示错误文字；停止状态不显示旧媒体错误。
- Camera Card 与 Detail 现在通过同一个展示状态入口组合 Session 和各自 video DOM 的首帧、暂停及
  播放错误，状态 Badge 使用同一个通用组件。Card 的空 WHEP URL 占位仍由 Cameras 模块处理。

## 影响

- Backend API、OpenAPI、数据库、环境变量、部署配置、WHEP 协议和 Session Lease 生命周期无变化。
- Card 仍只显示无文字 Spinner，不增加错误恢复控件；页面 hidden、视口、搜索翻页、路由离开、组件
  卸载和空 WHEP URL 的规则不变。
- Frontend Camera 派生类型统一从 Cameras API 边界导出，视频状态、音量和操作栏显隐测试按职责维护，
  方便后续 Camera 更新功能复用现有类型与播放器入口。

## 验证

使用纯状态、VideoSurface Hook、VideoControls、Camera Card 和 Camera Detail 测试覆盖三种操作栏模式、
三类媒体错误、Session 失败刷新、首帧 loading/超时、暂停、音量 Portal 与全屏组合。另执行 Frontend
全量测试、Lint、格式检查、生产构建、Cameras 敏感数据检查和 Git 差异检查。

当前规则见 [Camera 详情](../modules/cameras/camera-detail.md)与
[WHEP 浏览器播放](../modules/cameras/whep-player.md)。
