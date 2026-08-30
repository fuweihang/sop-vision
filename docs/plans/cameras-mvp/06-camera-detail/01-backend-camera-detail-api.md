# 06.1｜Backend Camera 详情接口

## 任务目标

实现 `GET /api/v1/cameras/{camera_id}`，让调用方可以读取 PostgreSQL 中的完整 Camera 配置，并附带
一次 MediaMTX Runtime Path 快照产生的 Source 与 Camera 状态投影。

本任务完成后，Backend 接口必须可以独立通过 Application、HTTP、持久化、错误和敏感数据测试；
Frontend 页面仍可以保持现状。

## 当前上下文与前置条件

- Camera 创建、领域聚合、PostgreSQL Repository/UoW、Stream Gateway Adapter 和后台媒体对账已经
  实现，当前事实见：
  - [Cameras 基础能力](../../../modules/cameras/foundation.md)
  - [Camera 创建](../../../modules/cameras/camera-create.md)
  - [Stream Gateway](../../../modules/cameras/stream-gateway.md)
- `CameraDetail`、`getCamera` OpenAPI、Frontend 生成类型、API Client、Fixture 和 MSW 场景已经存在；
  `get_camera` handler 当前仍是纯 `NotImplementedError` 占位。
- 现有 `CameraRepository.get(camera_id, for_update=False)` 会加载 Camera 和按 `sort_order` 排好的完整
  Source；`project_source_runtime()`、`summarize_camera_runtime()` 和
  `camera_detail_from_runtime()` 可以直接复用。
- 精确 HTTP Schema 以 `contracts/openapi.json` 为准。开始实施前先核对当前代码和生成物，保留用户
  已有未提交改动，不手动编辑 `frontend/src/routeTree.gen.ts`。

## 实施范围

### Application 读取流程

新增框架无关的 Camera 详情 Application Service 和有类型结果，直接依赖现有
`CameraUnitOfWork`、`StreamGatewayPort` 与 `Clock`：

1. 调用 `uow.cameras.get(camera_id, for_update=False)`，不得为详情读取加行锁。
2. 成功读取或确认不存在后，调用现有 `uow.rollback()` 结束只读事务，再访问 MediaMTX。这样最多
   `500ms` 的外部快照不会继续占用 PostgreSQL 事务和连接。
3. Camera 不存在时，结束事务后抛出带已校验 Camera ID 的 `CameraNotFoundError`，不得调用
   Stream Gateway。
4. 所有 Source 共享一次 `fetch_runtime_path_snapshot()`。只捕获 Port 声明的
   `StreamGatewayUnavailableError` 和 `StreamGatewayInvalidResponseError`；Adapter 失败时调用一次
   注入的 `Clock`，再使用现有批量投影函数生成同批降级状态。
5. 使用 `summarize_camera_runtime()` 校验 Source ID、顺序和数量并计算 Camera 状态，返回 Camera、
   按序 Source 投影和共享统计。不得在详情服务复制 Camera 状态规则或 HTTP Schema。

任务取消、未知程序错误和 Mapper 防御错误必须继续向上传播，不得为了返回部分详情而吞掉。

### HTTP、错误与日志

- Router 原位替换 `get_camera` 占位，注入请求级 UoW、lifespan Stream Gateway 和请求 Clock，使用
  现有 Mapper 返回 `CameraDetail`，并设置 `Cache-Control: no-store`。
- 让现有 `CameraNotFoundError` 保存规范化 Camera ID；现有 Repository/Application 抛出点同步传入
  ID。HTTP Handler 只把该字段白名单写入 `context.camera_id`。
- Repository 重建时若抛出 `CameraAggregateCorruptedError`，详情服务必须结束只读事务并转换为
  `CameraAggregateInvalidError`。新错误只保存请求 Camera ID，默认表示和消息不得包含底层 issues。
- 为 `CameraAggregateInvalidError` 增加独立 HTTP Handler，返回
  `500 CAMERA_AGGREGATE_INVALID`。现有 `CameraConstraintViolationError` 继续返回通用安全 500，不能
  因本任务改变其他接口的错误正文。
- 聚合损坏只记录一条 `camera.detail_aggregate_invalid` ERROR，字段固定为
  `operation=get_camera/outcome=failed/camera_id`。在现有日志事件注册表中登记字段和
  `camera.detail` component，并同步更新 `docs/modules/backend-logging/events.md`。
- 响应、日志和异常默认表示不得包含聚合对象、领域 issue、Source ID 列表、凭据、后缀、RTSP URL、
  SQL、约束名或底层 MediaMTX 响应。

### 测试

- Application 单元测试覆盖：成功、Camera 不存在、聚合损坏、全在线、全离线、混合状态、两类
  Stream Gateway 失败、快照只调用一次、事务结束顺序、无 MediaMTX 写调用和任务取消传播。
- API 测试覆盖：`200`、`no-store`、完整 `CameraDetail`、`404 CAMERA_NOT_FOUND` 与准确 context、
  `422` Canonical UUID、`500 CAMERA_AGGREGATE_INVALID`、`503 DATABASE_UNAVAILABLE` 和依赖替换。
- PostgreSQL 集成测试覆盖真实 Repository 详情读取和损坏聚合路径；必须证明 Source 顺序、默认源、
  计数和派生 RTSP URL 正确。
- 日志测试断言聚合损坏只产生一条已注册 ERROR，并执行现有敏感数据门禁。
- 占位门禁必须确认 `get_camera` 已实现，另外四个未实现 handler 仍是纯占位。

## 明确不做

- 不修改 Frontend 路由、Query、页面组件或样式。
- 不实现 WHEP Player、列表、编辑、默认源切换或删除。
- 不修改 `CameraDetail` 字段形状，不增加新的公开 DTO 或第二套状态枚举。
- 不调用 `ensure_path()`、`release_path()`，不增加重试、Outbox、Saga、Query Bus、Generic Repository
  或 Base Service。
- 不移除 06 计划，不新增最终 `docs/changes/` 交付记录；这些由 06.2 在完整页面完成后处理。

## 实施步骤

1. 为现有 Fake UoW/Repository、Stream Gateway 和 Clock 补齐详情测试需要的观察能力。
2. 增加详情 Application 错误、结果类型和读取服务，先通过 Application 单元测试。
3. 接入 Camera 不存在 context、聚合损坏 HTTP 映射和注册日志事件，补错误与日志测试。
4. 原位实现 `get_camera` Router，复用现有 Mapper，补 API 与 PostgreSQL 集成测试。
5. 更新 Backend 日志事件文档，运行完整 Backend、OpenAPI、敏感数据和占位门禁。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# backend/
uv run --env-file .env.local pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_camera_placeholders.py foundation
```

需要 PostgreSQL 的测试必须配置独立 `TEST_DATABASE_URL`。详情持久化或损坏聚合测试被跳过时，不能
宣称本任务完成。

## 完成标准

- `GET /api/v1/cameras/{camera_id}` 的成功、媒体降级、404、422、500 和 503 行为全部有测试且通过。
- 一次请求只读取一个聚合、结束一次只读事务并获取一次 Runtime Path 快照；没有媒体写调用。
- 运行响应和日志通过敏感数据检查，`get_camera` 不再是占位，其他占位生命周期不变。
- OpenAPI 字段形状和 Frontend 生成类型无意外漂移。

## 与 06.2 的衔接

06.2 开始前必须读取本任务的实际实现和测试结果，重点确认：

- `getCamera` 成功响应仍使用现有 `CameraDetail`。
- 404 的稳定分支是 `code=CAMERA_NOT_FOUND` 且 `context.camera_id` 准确。
- 聚合损坏的稳定分支是 `code=CAMERA_AGGREGATE_INVALID`。
- 数据库不可用仍是 `DATABASE_UNAVAILABLE`，媒体故障仍返回 `200` 降级详情。
- 若 OpenAPI 或生成类型确有变化，06.2 必须基于重新生成后的实际类型实施，不能复制本文件字段。
