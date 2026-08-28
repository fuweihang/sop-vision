# 2026-08-28｜Backend 统一日志

## 变化

- Backend、Uvicorn、SQLAlchemy 和 Alembic 使用统一的 console/JSON Formatter 与 stderr Handler。
- 业务日志改为简短中文消息和稳定事件字段；持续媒体故障只在首次、类型变化和每 30 分钟提醒时
  输出 WARNING，恢复时输出一条 INFO。
- Uvicorn 原生 access log 被应用级完成日志替代；每个请求最多一条，并保留实际状态、完整耗时和
  trace。
- SQL 输出改由 `DATABASE_ECHO` 单独控制，Runtime 始终隐藏绑定参数。

## 影响

- 新增 `BACKEND_LOG_LEVEL`、`BACKEND_LOG_FORMAT` 和 `TZ` 配置；`DATABASE_ECHO` 保留原开关用途，
  但不再启用 SQLAlchemy 自带 echo Handler。
- HTTP API、OpenAPI、数据库结构和前端行为无变化。
- 日志文本存在不兼容变化。外部采集、正则和告警不能继续解析旧的完整 console 文本，应设置
  `BACKEND_LOG_FORMAT=json` 并读取 `event`、`outcome`、`trace_id` 等稳定字段。
- HTTP query、正文、headers、客户端信息、数据库绑定参数、完整连接串、RTSP URL 和原始异常文本
  不进入统一日志；这不替代部署侧访问控制和 Secret 管理。

## 验证

使用 Backend 日志、HTTP middleware、数据库 Engine、Alembic、启动入口和业务事件测试验证两种
格式、级别、去重、故障提醒、恢复事件与敏感数据过滤；同时执行 Backend pytest、Ruff、MediaMTX
检查和 Compose 配置检查。PostgreSQL 迁移与 Repository 路径使用独立 `TEST_DATABASE_URL` 验证。

当前规则见 [Backend 日志](../modules/backend-logging/README.md)。
