# 01｜Camera 列表 API

## 任务目标

实现 `GET /api/v1/cameras`（`listCameras`），让调用方可以按名称或 IPv4 搜索并稳定分页读取非敏感
Camera 摘要。当前页所有 Source 使用一次 MediaMTX Path 快照生成状态；媒体失败不阻断配置读取。

本任务完成后，Backend API、受控 OpenAPI、Frontend 生成类型和 MSW Fixture 具备最终列表契约，后续
页面任务可以直接依赖，不再使用占位 handler。

## 当前上下文与前置条件

- 先阅读 [Cameras 基础能力](../../../../modules/cameras/foundation.md)、
  [Stream Gateway](../../../../modules/cameras/stream-gateway.md)和
  [Camera 详情](../../../../modules/cameras/camera-detail.md)。
- `CameraRepository.list/count` 已支持字面包含搜索、固定排序和批量 Source 读取；不得在 Application
  或 Router 中重新实现 SQL 搜索与排序。
- `CameraListParameters`、`CameraPage/CameraSummary`、`listCameras` Frontend Client、Query Key、Fixture
  和 MSW handler 已预留，但 Backend `list_cameras` 仍是纯占位。
- `summarize_camera_runtime` 和 Stream Gateway 投影函数是状态规则的现有实现，列表必须复用。
- 现有 `CameraAggregateInvalidError` 属于单 Camera 详情错误并强制携带 `camera_id`；批量列表不得为了
  复用它而猜测、暴露或重新查询损坏条目 ID。本任务新增不携带请求数据的列表级 Application 错误，
  详情错误类型和详情响应保持不变。
- 精确公共 Schema 以 `contracts/openapi.json` 为准。修改 Backend Schema 或响应状态后必须重新导出
  OpenAPI 并生成 Frontend 类型，不能手改 `frontend/src/generated/openapi.ts`。

## 实施范围

### 查询与事务

- `q` trim 后对 Camera 名称和 IPv4 做大小写无关的字面包含搜索；空白等同未提供。
- `%`、`_`、`\` 是普通字符，不是 SQL 通配符。查询继续使用绑定参数。
- 默认 `page=1`、`page_size=20`；`page >= 1`、`1 <= page_size <= 100`。
- 先按同一条件 count，再按 `created_at ASC, camera_id ASC` 读取当前页；越界页返回空 `items` 和真实
  `total`。额外查询参数继续忽略。
- count 和当前页聚合读取完成后显式结束只读事务，再访问 MediaMTX。正常、空页、损坏聚合和数据库
  失败路径都不能把数据库事务保留到外部 I/O 阶段。

### 批量运行态投影

- 空页直接返回，不访问 Stream Gateway。
- 非空页只调用一次 `fetch_runtime_path_snapshot()`；不得按 Camera 或 Source 调用 Control API。
- 使用同一快照投影当前页全部 Source，再按每个 Camera 的 Source 顺序复用
  `summarize_camera_runtime` 计算 `ONLINE/OFFLINE/DEGRADED` 和在线计数。
- 只有严格 `ONLINE` 的默认 Source 返回 `whep_url`；其他情况返回 `null`。
- MediaMTX 不可用或响应无效时仍返回 `200`。当前页全部 Source 使用同一个失败完成时间和稳定离线
  错误，列表读取不创建、修复或释放 Path。

### HTTP 与错误

- 响应为 `{items, page, page_size, total}`，字段严格遵守 08 主计划的非敏感白名单。
- 当前页任一聚合无法重建时，不返回部分列表、不访问 MediaMTX，返回脱敏的
  `500 CAMERA_AGGREGATE_INVALID`。Application 捕获 `CameraAggregateCorruptedError` 后先结束只读事务，
  再从 `except` 外抛出不携带 `camera_id`、损坏项或原始输入的列表级错误，避免异常上下文把领域损坏
  详情带到 HTTP 或日志。列表错误不得包含损坏 Camera 的字段、凭据或 Source 后缀。
- 数据库读取或结束事务失败返回 `503 DATABASE_UNAVAILABLE`；查询参数非法返回 `422`。
- 列表级错误与现有详情错误共用 `500 CAMERA_AGGREGATE_INVALID` Problem 响应构造，但分别注册异常
  类型；不得把详情错误的 `camera_id` 改成可空字段。同步更新 Router 声明、OpenAPI 响应集合和契约
  测试。列表成功响应不需要 `Cache-Control: no-store`，但仍只允许内存 Query cache。

## 明确不做

- 不实现 `/cameras` 页面、URL search 参数、分页控件或 Card UI。
- 不调用 `ensure_path/release_path`，不修改 Reconciler 或 Stream Gateway 协议。
- 不实现 Card/Detail 共享播放、IntersectionObserver 或页面可见性处理。
- 不实现 09、10 的写接口，也不清除这些 handler 的占位状态。

## 实施步骤

1. 新增框架无关的 Camera 列表 Application Service、结果类型和无请求数据的列表聚合损坏错误，组合
   Repository、UoW、Clock 与 Stream Gateway；明确所有事务结束、异常上下文切断和错误转换分支。
2. 为批量结果增加显式 API Mapper。逐字段构造 `CameraSummary`，定位每个 Camera 的默认 Source，
   不允许从 `CameraDetail`、领域对象字典或 ORM Row 直接展开响应。
3. 将 `list_cameras` Router 占位替换为真实依赖装配，把列表级错误单独注册到现有聚合损坏 Problem
   响应，并声明稳定 `500`；保持详情错误类型及其 handler 行为不变。
4. 覆盖 Application 单元测试：空页、全在线、全离线、混合、默认源离线、快照两类失败、单快照、
   不执行媒体写操作及事务结束。
5. 覆盖 Repository/API 集成测试：默认参数、名称/IP 搜索、空白搜索、`%/_/\`、稳定分页、越界页、
   额外参数、非法分页、数据库故障、聚合损坏和响应脱敏。
6. 更新并导出受控 OpenAPI，重新生成 Frontend 类型，调整契约、Fixture 和 MSW 测试中的最终响应
   状态。连续执行两轮生成并比较 SHA-256，确认第二轮没有继续改变产物；审查两个生成文件的预期
   diff，并确认占位门禁只剩 09、10 对应 handler。
7. 更新 Cameras 当前能力文档，说明列表 API 已完成但列表页面和 Card 播放仍由 02、03 待实现；新增
   对应阶段变更记录。不要提前移除整个 08 计划。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-sensitive-data.sh

# backend/
uv run --env-file .env.local pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_camera_placeholders.py foundation

# frontend/
pnpm test
pnpm lint
pnpm format:check
pnpm build

# 首轮生成后在 frontend/ 记录受控产物摘要，再执行第二轮生成并比较。
cd ../backend
uv run python scripts/export_openapi.py
cd ../frontend
pnpm api:generate
first_contract_hashes="$(sha256sum ../contracts/openapi.json src/generated/openapi.ts)"
cd ../backend
uv run python scripts/export_openapi.py
cd ../frontend
pnpm api:generate
test "$first_contract_hashes" = "$(sha256sum ../contracts/openapi.json src/generated/openapi.ts)"
git diff -- ../contracts/openapi.json src/generated/openapi.ts
```

PostgreSQL 集成测试必须配置独立 `TEST_DATABASE_URL`；相关测试被跳过时不能把持久化验收记为通过。
`bash scripts/check-cameras-contracts.sh` 会把尚未提交的预期生成物变更视为漂移，因此不作为当前实现
工作区的通过条件；生成物提交后或 CI 的干净工作区仍必须运行该门禁。

## 完成标准

- `GET /api/v1/cameras` 不再是占位，OpenAPI 声明 `200/422/500/503`。
- 搜索、count、固定排序、分页、空页和越界页行为与 Repository 公共规则一致。
- 非空页固定一次 Path 快照，空页和损坏聚合不访问 MediaMTX。
- 媒体故障返回确定的 `200` 降级状态；数据库和损坏聚合错误分别稳定映射为 `503` 与 `500`。
- 列表聚合损坏错误不携带 Camera ID 或领域损坏项，详情聚合损坏错误仍保留原有单 Camera 行为。
- 列表响应、Problem、日志、Fixture 和测试输出不包含敏感字段。
- Backend、敏感数据和 Frontend 检查全部通过；OpenAPI 与生成类型连续两轮生成结果一致，预期 diff
  已审查。当前未提交工作区不把契约脚本的预期漂移结果记为失败，生成物提交后的干净工作区或 CI
  必须再通过该门禁。

## 与下一任务的衔接

下一步执行 [02｜Camera 列表页面](../02-camera-list-page/README.md)。02 必须复用本任务生成的
`CameraPage/CameraSummary` 类型、`listCameras` Client 和最终错误契约，不得在 Frontend 猜测状态、
默认 Source 或 WHEP URL。
