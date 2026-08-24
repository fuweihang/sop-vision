# 步骤 8｜前端状态基元与 Mock Server

> 前置：[步骤 7](./07-frontend-client.md)  
> 产出：Cameras 页面状态基元、类型安全 Fixture、MSW 场景切换入口

## 1. 完成目标

为 02–09 功能切片提供可复用的页面状态和 HTTP Mock，使各切片无需真实 Backend、PostgreSQL、摄像头或 MediaMTX 即可开发和测试。

## 2. 页面状态基元

在现有 Route State 与 design system 基础上补齐 Cameras 所需语义，不创建完整业务页面：

- 首次加载：无旧数据时使用稳定骨架。
- 后台刷新：保留旧内容并提供非阻塞反馈。
- 空数据：没有任何 Camera，提供创建入口插槽。
- 搜索无结果：保留搜索上下文并提供清除入口。
- 可恢复错误：区分整页首次失败和保留旧内容的刷新失败。

基元以组合能力或 slot 接收业务操作，不能内置尚未实现的创建、重试或路由逻辑。空数据和搜索无结果必须是不同状态。

## 3. MSW 结构

建议结构：

```text
frontend/src/test/mocks/cameras/
├── fixtures.ts
├── handlers.ts
├── scenarios.ts
└── server.ts
```

- Fixture 使用步骤 7 的生成类型，并通过 `satisfies` 保持编译期校验。
- 使用固定 UUID v4、UTC 时间，并按 `created_at ASC, camera_id ASC` 固定排序，使快照可复现。
- 场景切换以测试/Story 入口显式选择，禁止通过全局随机数或执行顺序改变结果。
- handlers 模拟业务文档的目标成功契约和媒体类型，但 Mock 成功不证明 Backend handler 已经
  替换 `NotImplementedError`。

## 4. 最小场景集合

- 成功：空列表、单 Camera、多页列表、Camera 详情、Playback 可用。
- 字段失败：创建/更新嵌套 Source 的 `422 VALIDATION_ERROR`。
- 资源失败：Camera/Source `404`。
- 播放未就绪：`409 PLAYBACK_NOT_AVAILABLE`。
- 媒体响应无效：`502 MEDIA_SERVICE_INVALID_RESPONSE`。
- PostgreSQL/MediaMTX 必需依赖不可用：对应 `503`。
- 首次请求失败和后台刷新失败。

错误响应必须使用 `application/problem+json` 并含 trace ID。成功 Fixture 中，列表和 Playback 不得包含凭据；详情凭据只使用明确的测试值。

## 5. 实施顺序

1. 建立生成类型约束的固定 Fixture Builder。
2. 实现默认 handlers 和每类 Problem handler。
3. 实现场景选择、每例 reset 和未处理请求失败策略。
4. 将 MSW server 接入 Vitest setup，确保测试间无状态泄漏。
5. 实现五类页面状态基元及可访问性测试。
6. 添加一个无业务页面的 harness，证明状态和场景可独立切换。

## 6. 必测场景

- 每个测试结束后 handlers、计数器和临时场景恢复默认值。
- 未声明 API 请求使测试失败，避免静默访问真实网络。
- Fixture 全部通过生成类型，并满足 UUID/时间/敏感字段边界。
- `422` 能驱动动态 Source 行错误；404/409/502/503 保持稳定 code。
- 首次加载与后台刷新呈现不同，后台失败不清空旧内容。
- 空数据与搜索无结果具有不同标题和操作。
- 状态基元具备合理的 `aria-live`、焦点和重试按钮语义。

## 7. 退出条件

- 任一后续功能切片可一行选择场景并启动测试，不复制 handlers。
- MSW 测试绝不访问真实 Backend 或 MediaMTX。
- 状态基元不包含具体 Camera CRUD 实现。
- Frontend test、lint、format check 和 build 通过。

## 8. 后续交接

业务切片可以扩展自己拥有的场景，但公共 Problem、ID、时间和 Camera Fixture 必须复用本步骤
Builder；修改公共形状时先更新 OpenAPI 和生成类型。MSW 只模拟目标业务契约，不模拟或
稳定化 Backend 占位 handler 的 `NotImplementedError` 临时结果。
