# Cameras 模块文档维护约束

## 单一事实源

- `README.md` 维护当前能力索引、模块边界和未实现范围。
- `foundation.md` 维护数据、事务、HTTP、敏感数据和跨端公共规则。
- `mediamtx-contract.md` 维护外部协议、版本和部署边界。
- `stream-gateway.md` 维护 MediaMTX Adapter、快照和状态投影。
- `media-reconciliation.md` 维护后台恢复、并发锁、退避和 Path 生命周期。
- 每个已实现业务用例使用按能力命名的独立文档，例如 `camera-create.md`。

精确 HTTP Schema 以 `contracts/openapi.json` 为准；代码、迁移和自动化测试优先于文字说明。公共
规则只写入一个文件，其他位置使用链接，不复制完整字段、Path 命名、排序或敏感数据规则。

## 修改流程

1. 先核对当前代码、迁移、OpenAPI 和测试，再修改对应文档。
2. 功能完成后更新模块入口和对应能力文档，不保留实施步骤和进度日志。
3. API 变化时同步 Backend Schema、OpenAPI、生成类型和 Fixture。
4. 同时在 `docs/changes/` 新增交付记录，再从 `docs/plans/` 移除完成任务。
5. 修改后检查相对链接、重复规则和 Markdown 格式。

不得添加手工更新时间、测试通过数量或提交列表。Git 历史保存开发过程。
