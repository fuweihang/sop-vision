# 05.1｜Backend Camera 创建 API

> 状态：已完成
>
> 父方案：[05｜创建 Camera](README.md)
>
> 后续任务：[05.2｜Frontend Camera 新增 Dialog](02-frontend-camera-create-dialog.md)

## 任务目标

把 Foundation 中的 `createCamera` 占位 handler 原位替换为真实
`POST /api/v1/cameras`：在单个数据库事务内创建 Camera 聚合，提交后尽力同步 MediaMTX，并使用一次
运行态快照返回 `201 CameraDetail`。该任务完成时，接口应能被独立调用、自动化测试和契约门禁验证，
不依赖 Frontend 已实现。

## 当前上下文与前置条件

新会话开始时必须先完整读取父方案、`docs/cameras-mvp/AGENTS.md`、根 Cameras MVP、01、03、04 和 06
文档，并核对当前代码与测试，不能假设本文件生成后代码状态没有变化。

当前已知基础如下：

- Foundation 已提供 Camera 聚合、`Camera.create`、Repository/UoW、SQLAlchemy 实现、Fake、Schema、
  Problem 映射、固定 UUID/Clock 测试替身和七个占位 handler。
- 03 已提供 `StreamGatewayPort`、`project_source_runtime`、严格 Source 状态和 WHEP URL。
- 04 已提供 `build_camera_desired_sources` 和后台对账。创建提交后的即时 `ensure_path` 仍属于本任务。
- `CameraCreateRequest`、`CameraDetail`、OpenAPI、Frontend 生成类型和 `createCamera` Client 已存在；不要
  重新设计 HTTP 形状。
- 当前 `sources=[]` 会被公共 Pydantic 转换器错误映射为 `OUT_OF_RANGE`，本任务必须修正为
  `SOURCE_REQUIRED`，同时保留 OpenAPI `minItems=1`。
- `CameraStatus` 当前位于 API Schema。共享 Camera 状态规则必须移入 Cameras Application，Schema
  复用同一枚举，Application 不能依赖 FastAPI/Pydantic。

开始修改 FastAPI endpoint 前，按仓库可用的 `develop-fastapi-endpoint` 技能检查项目约定；涉及依赖
API 的用法时按仓库规则使用 Context7 当前文档。

## 实施范围

### Application 与状态组装

- 增加框架无关的创建用例，显式接收创建命令、请求级 `CameraUnitOfWork`、共享
  `StreamGatewayPort`、`IdGenerator` 和 `Clock`。
- 使用 `Camera.create` 生成完整合法聚合，不在 Router、Service 和 Domain 各复制一套规范化规则。
- `add` 后显式 `commit`；`add` 或 `commit` 失败时保证回滚并停止，提交前零 MediaMTX 调用。
- 数据库提交后按 Source 顺序调用 `build_camera_desired_sources` 与 `ensure_path`。只捕获 Port 声明的
  MediaMTX 不可用/无效响应并继续其余项；不重试、不修改已提交数据库、不吞任务取消。
- 全部即时同步尝试后只取一次完整 Runtime Path 快照。Adapter 失败转换为同一检查时间下的批量
  离线投影；成功快照按 03 规则投影，只有严格在线 Source 有 `whep_url`。
- 在 Cameras Application 定义唯一 `CameraStatus` 和不可变聚合结果。纯函数校验 Camera Source 与
  Source 投影的 ID、顺序和数量，计算状态、在线数和配置总数。
- 创建用例返回包含 Camera、按序 Source 投影和 Camera 聚合结果的有类型结果，不能返回 Pydantic
  Schema 或 ORM Row。

### HTTP 与依赖装配

- 增加 API 层 `CameraDetail` 映射能力，按聚合顺序返回 Source，使用领域方法派生展示用完整 RTSP
  URL；不得使用发给 MediaMTX 的百分号编码 URL 代替展示 URL。
- 原位实现 POST handler，返回 `201`、`Location: /api/v1/cameras/{camera_id}`、
  `Cache-Control: no-store` 和现有 Trace Header。
- 使用现有请求级 UoW 与 lifespan 级 Stream Gateway 依赖；为生产 `Uuid4Generator`、`SystemClock`
  提供可替换装配点，API 测试能够注入固定 ID、时间、UoW 和 Gateway。
- 为 `CameraCreateRequest.sources` 的空数组增加不携带输入值的自定义 Pydantic 错误类型，并让公共
  校验转换器仅按类型映射 `SOURCE_REQUIRED`。保留现有 `min_length=1` 生成的 OpenAPI 约束。
- 用户输入重复后缀继续由 Domain 在写库前返回带准确数组下标的 `422`。无法可靠定位字段的数据库
  约束沿用安全服务端错误，不能公开 SQL、参数、约束名或猜测字段。
- MediaMTX 在数据库提交后失败不得改变 `201`；数据库不可用仍返回
  `503 DATABASE_UNAVAILABLE`。

### 测试与文档状态

- 增加纯状态聚合、创建用例、响应映射和真实 Router 集成测试；复用现有 Fake，不为一个测试再建立
  第二套通用 Repository 或 Service 框架。
- 测试固定 UUID/Clock、1/2/10 路 Source、事务失败、媒体单项失败、快照失败、在线/离线/混合状态、
  Location/no-store 和敏感数据。
- PostgreSQL 集成测试覆盖 flush/commit 失败完整回滚；未配置独立 `TEST_DATABASE_URL` 时可跳过，
  但任务结果必须明确说明没有完成这部分验收。
- 仅在 API 形状真实变化时导出 `contracts/openapi.json` 并运行 Frontend 类型生成；生成文件不能手改。
- 完成后可以把本任务状态改为已完成，但不得提前把父方案或根状态表中的 05 改为已完成。

## 明确不做

- 不实现 `GET /cameras`、`GET /cameras/{camera_id}` 或其他 Camera handler。
- 不修改 `/cameras` Frontend 页面、Dialog、MSW 交互场景或播放器。
- 不增加请求幂等键、数据库唯一业务键、保存前 RTSP 探测、Outbox、Saga、媒体补偿或通用 CRUD
  Service。
- 不把 MediaMTX 调用放进数据库事务，不因媒体失败删除已创建 Camera。
- 不把 Camera 状态规则放入 Stream Gateway，也不复制 Application/API 两套状态枚举。
- 不记录请求 DTO、Camera 聚合、凭据、完整 RTSP URL、MediaMTX 原始响应或底层数据库异常文本。

## 实施步骤

1. 重新核对父方案、现有占位门禁、Schema、Domain、UoW、Adapter 投影和测试替身。
2. 先实现并测试 Application 的 Camera 状态枚举、聚合函数和创建结果类型。
3. 实现创建用例及事务后媒体同步，覆盖数据库失败零媒体调用和媒体失败继续响应。
4. 实现 API 映射、UUID/Clock/Gateway/UoW 依赖装配与 POST handler。
5. 修正 HTTP 空 Source 错误，同时断言 OpenAPI `minItems=1` 未丢失。
6. 补齐 Router、持久化、敏感数据和占位生命周期测试；只修复本任务引入的问题。
7. 运行全部 Backend 与跨端契约门禁，检查 diff 中没有无关代码或生成物漂移。

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

还要执行以下行为检查：

- POST 单/双/十 Source 均返回完整 `201 CameraDetail`，ID、时间、顺序、默认源和计数确定。
- 空 Source 返回 `sources/SOURCE_REQUIRED`，无默认、多默认和重复后缀返回父方案规定字段错误。
- `add`、flush、commit 任一失败均零 MediaMTX 调用且数据库无部分聚合。
- 提交后部分或全部 `ensure_path` 失败仍继续；Runtime 快照每个请求最多一次。
- Gateway 不可用/无效、Path 缺失/未就绪/离线均返回确定降级投影和 `whep_url=null`。
- 日志、异常、Problem、列表/Playback 既有契约与测试生成物中没有测试密码或完整 RTSP URL 泄漏。

## 完成标准

- `createCamera` 已不再是占位，真实应用可以调用并得到父方案规定的成功或错误响应。
- 创建事务、提交后媒体同步、共享状态聚合与 CameraDetail 映射均有确定测试。
- 其余六个 Camera handler 仍保持 Foundation 占位，`foundation` 占位门禁通过。
- Backend 全量测试、Ruff、格式、契约与敏感数据脚本通过；PostgreSQL 验收若跳过已明确报告。
- 没有实现本任务“明确不做”的功能，父方案和根状态仍显示 05 未完成。

## 与下一任务的衔接

05.2 开始前应读取本任务最终 diff、实际 OpenAPI 和 Backend 测试，确认以下事实：

- `createCamera` 请求/响应类型是否发生生成层变化；若发生，只使用重新生成的类型。
- `422` 的字段路径和 code、`503 DATABASE_UNAVAILABLE`、Location/no-store 与未知提交结果边界。
- 创建成功不会要求跳转详情或立即播放，前端只需失效 `["cameras"]` 前缀。
- 父方案和根状态仍未完成，必须等 05.2 验证通过后统一更新。
