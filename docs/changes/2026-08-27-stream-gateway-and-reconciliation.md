# 2026-08-27｜Stream Gateway 与媒体对账

## 变化

- 实现 MediaMTX Path 读写、配置与运行态快照、Source 状态投影和 WHEP URL 构造。
- Backend 启动后立即执行媒体对账，并按周期从 PostgreSQL 恢复缺失或漂移的受管 Path。
- 多实例通过 PostgreSQL advisory lock 避免重复对账；依赖故障使用退避和抖动重试。

## 影响

- Backend 可在 MediaMTX 重启后自动恢复 Path，并清理数据库中已不存在的受管孤儿 Path。
- MediaMTX 故障不会让 Camera 配置 API 整体失去就绪状态。
- 新增对账周期、超时和重试相关运行配置；HTTP API 与数据库结构无变化。

## 验证

使用 Adapter Fixture、真实 MediaMTX 测试、对账单元测试和 PostgreSQL 集成测试验证。

当前规则见 [Stream Gateway](../modules/cameras/stream-gateway.md)和
[媒体对账](../modules/cameras/media-reconciliation.md)。
