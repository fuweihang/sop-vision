# 05｜09 集成验收与文档收尾

## 任务目标

以 01–04 已落地的真实代码、OpenAPI、生成类型和测试为输入，完成 09 的跨端组合验收；把最终能力、
故障边界和排查信息写入长期文档，新增交付记录，并按计划完成规则移除 09。

本任务不补做缺失业务能力。发现失败时回到对应事实所有者修复并重新执行验收，不能在这里增加第二份
规则、临时兼容分支或只为测试通过的绕过。

## 当前上下文 / 前置条件

- 以下任务必须全部完成并各自通过验证：
  1. [01｜Backend Camera 完整更新](../01-backend-camera-update/README.md)
  2. [02｜Backend 默认预览源切换](../02-backend-default-preview-source/README.md)
  3. [03｜Frontend Camera 编辑 Dialog](../03-frontend-camera-edit/README.md)
  4. [04｜Frontend 默认源与播放器联动](../04-frontend-default-preview-source/README.md)
- 开始前读取 [09 总计划](../README.md)、[Cameras 模块](../../../../modules/cameras/README.md)、
  [Cameras 基础能力](../../../../modules/cameras/foundation.md)、
  [媒体对账](../../../../modules/cameras/media-reconciliation.md)、
  [WHEP 浏览器播放](../../../../modules/cameras/whep-player.md)和
  [执行计划完成规则](../../../README.md#完成规则)。
- 当前代码、迁移、`contracts/openapi.json`、Frontend 生成类型、测试和运行行为优先于 01–04
  文件中的实施假设。先核对实际结果，再写长期文档。
- PostgreSQL 集成测试必须配置独立 `TEST_DATABASE_URL`；相关测试跳过时不能进入文档收尾。

## 实施范围

### 契约与自动化验收

- 确认 PUT、PATCH 已由真实 Application Service 和生产依赖装配，Camera 删除仍是唯一允许保留的
  Cameras 占位 handler。
- 检查 Backend Schema、Router、错误响应、受控 OpenAPI、Frontend 生成类型、Client、MSW 与 Fixture
  无漂移。
- 覆盖 Camera/Source 增删改排、默认源约束、连接字段变化、稳定 ID/时间、Source 所有权、损坏聚合
  和精确媒体 diff。
- 使用独立 PostgreSQL 验证已知事务失败回滚、完整聚合原子保存、同 Camera PUT/PUT 与 PUT/PATCH
  写入按锁串行，以及最终数据库状态对应最后完成的合法更新。
- 使用可控 Stream Gateway 和对账测试验证 ensure/release/快照单项失败不改变已提交配置，下一轮按
  数据库状态恢复缺失、漂移或孤儿 Path。
- 验证 Frontend 确定失败/结果未知、草稿刷新保护、关闭/路由/浏览器离开、提交禁用、缓存失效及
  Mutation 敏感数据回收。
- 验证默认源在线/离线、Detail 排序自动选择/临时选择、默认源修改不替换 Detail 当前流、停止预览、
  Card/Detail 同源共享和 ID/URL 变化时的 Lease 切换。

### Synthetic 浏览器验收

- 使用 WHEP 模块已有的两路视觉可区分 synthetic RTSP/WHEP Source，不新增第三套测试源或媒体工具。
- 浏览器中完成 Camera 编辑、连接字段/Source 变化、默认源 PATCH、Detail 保持排序第一路或临时
  Source、离线默认源、Card 与 Detail 同源共享及最后一个 Lease 释放。
- Synthetic 冒烟只证明 09 的确定交互和浏览器生命周期，不替代真实设备、网络和容量发布门禁。

### 长期文档与计划处理

- 新增或更新 Cameras 对应能力文档，记录已经实现的 PUT/PATCH 行为、Frontend 编辑和默认源交互、
  错误/结果未知、媒体同步边界及排查入口。公共字段、事务、敏感数据和播放器规则继续引用现有唯一
  事实源，不在多个文件复制完整规则。
- 更新 `docs/modules/cameras/README.md` 当前能力、可用 handler 和未实现范围；编辑/默认源不再标为
  未实现，Camera 删除仍指向剩余计划。
- 按实际变化更新 `camera-detail.md`、`media-reconciliation.md`、`whep-player.md` 等事实所有者；
  只有形成独立业务用例时才新增相应能力文档。
- 在 `docs/changes/` 新增一条 09 交付记录，说明用户可见行为、API/配置影响、验证方式和仍由 11
  负责的边界；不记录测试数量、提交列表或手工更新时间。
- 全部验收和文档检查通过后，从 `docs/plans/cameras-mvp/README.md` 移除 09 条目，并删除整个
  `09-camera-update-default-source/` 计划目录。Git 历史保存拆分文件，不归档已完成计划。

## 明确不做

- 不实现 Camera 删除；下一阶段仍是 [10｜Camera 删除](../../10-camera-delete/README.md)。
- 不执行真实 MediaMTX 停机/重启、数据库提交后进程崩溃、多 worker/实例、真实 IPC/Codec、HTTPS、
  NAT、长时间连接或 20 Camera 容量门禁；这些属于
  [11｜发布门禁](../../11-release-gates/README.md)。
- 不新增公共路由、字段、错误码、UI 功能、兼容分支或通用测试框架。
- 不把计划实施步骤、临时决策或测试通过数量复制到长期模块文档。
- 任一必要检查失败或 PostgreSQL 测试跳过时，不更新任务状态、不写完成记录、不移除 09。

## 实施步骤

1. 核对 01–04 实际代码和测试，确认两个 handler、跨端契约、Query/Mutation 和播放器联动均已落地。
2. 配置独立 PostgreSQL，执行 Backend、Frontend、契约、敏感数据和静态检查；先修复所有失败。
3. 执行可控对账恢复测试和双路 synthetic WHEP 浏览器冒烟，记录需要回到前序能力修复的问题。
4. 在全部行为通过后，根据实际代码更新 Cameras 当前能力和相关事实所有者文档。
5. 新增 `docs/changes/` 交付记录，检查 Markdown 相对链接、重复规则和敏感信息。
6. 最后移除上级计划中的 09 条目和本计划目录，确认 10 成为下一项待实施能力。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# backend/
uv run --env-file .env.local pytest
uv run ruff check .
uv run ruff format --check .

# frontend/
pnpm vendor:check
pnpm test
pnpm lint
pnpm format:check
pnpm build
```

另外执行双路 synthetic WHEP 浏览器冒烟，并检查新增/修改 Markdown 的全部相对链接。必须确认
PostgreSQL 集成测试实际执行而不是 skip。

## 完成标准

- PUT/PATCH、跨端契约、数据库事务/并发、媒体 diff/恢复、编辑 Dialog、默认源和 Session 联动组合
  后全部通过。
- 请求、响应、Problem、日志、通知、错误上报和 Mutation cache 保持新旧密码、Source 后缀和完整
  RTSP URL 的既有敏感数据边界。
- Cameras 模块文档和交付记录准确反映实际实现，不复制公共规则或留下“编辑未实现”旧说明。
- 09 已从剩余计划和文件系统移除，10 成为下一项待实施任务；11 的真实依赖边界保持不变。

## 与下一任务的衔接

09 完成后执行 [10｜Camera 删除](../../10-camera-delete/README.md)。任务 10 应读取 09 完成后的当前
代码和模块文档，复用已经落地的 Camera 写事务、结果未知处理和共享 Lease 规则，不再引用已删除的
09 拆分文件。
