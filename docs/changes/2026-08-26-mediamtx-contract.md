# 2026-08-26｜MediaMTX 接入契约

## 变化

- MediaMTX 镜像和受控协议固定为 `v1.20.1`。
- Backend 增加 Stream Gateway Port、MediaMTX 健康依赖和公开 WHEP 地址配置边界。
- 明确 PostgreSQL 保存 Desired State，MediaMTX 配置允许丢失并由 Backend 重建。

## 影响

- 部署需提供 Backend 可访问的 MediaMTX Control API；Frontend 不得访问 Control API。
- MediaMTX 升级必须同步审查受控 OpenAPI、Fixture 和真实协议测试。
- HTTP API 与数据库结构无变化。

## 验证

使用受控协议测试、真实 MediaMTX Adapter 测试和 Compose 配置检查验证。

当前规则见 [MediaMTX 契约](../modules/cameras/mediamtx-contract.md)。
