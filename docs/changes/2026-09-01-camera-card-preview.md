# 2026-09-01｜Camera Card 实时预览

## 变化

- `/cameras` 中默认 Source 的 `whep_url` 非空时，Card 自动显示静音、无 controls 的实时预览；地址
  为空时不创建 video 或媒体会话，显示“不可预览”。
- Card 在连接、重连和等待当前 video 首帧期间显示 loading；左上角状态组合 Session 和当前 video
  出画结果，只有首帧真正渲染后才显示 `LIVE`，等待超过 `10s` 显示“画面超时”。底部保留默认 Source
  名称，不显示 Backend Source 状态。
- Card 复用现有 `StreamSessionManager`。同一路 Source 的多个 Card 或 Card 与 Detail 共享一个 reader
  和 MediaStream，但保留各自的 video DOM。
- Card 在挂载期间持续持有 Lease，不按视口相交比例或页面 hidden 状态暂停。搜索或翻页替换结果、
  离开路由、组件卸载、`whep_url` 改变或变为空时释放旧 Lease；最后一个消费者释放后停止 Track。

## 影响

- Backend API、OpenAPI、数据库、环境变量和部署配置无变化；Card 只消费列表已有的非敏感默认 Source
  摘要，不请求 CameraDetail，也不拼接媒体地址。
- `whep-player` MSW 场景的列表和详情现在返回相同的默认 `source_id+whep_url`，用于验证跨路由共享
  Session。
- 当前 UI 首屏默认最多展示 12 路预览；更高并发、真实 IPC、Codec、HTTPS 和 NAT 组合仍由 Cameras
  发布门禁验证。

## 验证

使用组件与路由测试覆盖无 URL、Session 状态、首帧 loading/超时、页面 hidden、搜索、翻页、URL
变化、Strict Mode、Card+Card 和 Card+Detail 共享。使用 Compose MediaMTX、synthetic RTSP Source 与浏览器检查实时画面、
静音、后台标签保持、跨路由复用，以及离开 Cameras 后 Track 停止；同时执行 Frontend 测试、Lint、
格式检查、生产构建、vendored 文件和 Cameras 合同/敏感数据检查。

当前规则见 [Camera 列表](../modules/cameras/camera-list.md)与
[WHEP 浏览器播放](../modules/cameras/whep-player.md)。
