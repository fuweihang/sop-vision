# 2026-08-28｜Camera 创建

## 变化

- `POST /api/v1/cameras` 从占位路由变为可用业务 API，一次创建 Camera 与完整 Source 集合。
- 创建先提交 PostgreSQL，再尽力同步 MediaMTX；媒体故障返回成功配置和降级运行态。
- Frontend `/cameras` 页面新增 Camera Dialog，支持动态 Source、默认源选择和字段错误定位。

## 影响

- API 成功返回 `201 CameraDetail`、`Location` 和 `Cache-Control: no-store`。
- 创建请求不会预先探测 RTSP；合法的离线 Camera 也能保存。
- 网络中断或 `503` 可能使客户端无法判断写入结果，Frontend 不会自动重试，以免重复创建。
- 数据库结构和既有配置项无变化。

## 验证

使用 Backend 创建 API 与事务测试、Frontend Dialog 测试、契约检查和敏感数据检查验证。

当前规则见 [Camera 创建](../modules/cameras/camera-create.md)。
