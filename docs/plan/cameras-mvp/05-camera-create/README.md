# 05｜创建 Camera

> 状态：已完成
>
> 前置：[Foundation](../01-foundation/README.md)、[Stream Gateway Adapter](../03-stream-gateway-adapter/README.md)、[媒体对账](../04-media-reconciliation/README.md)
>
> 交付：`POST /api/v1/cameras`（`createCamera`）和 Cameras 列表页中的新增表单 Dialog

## 职责与边界

本切片让用户一次录入 Camera 连接信息和完整 Source 数组，指定唯一默认源，并用一个数据库事务
创建聚合。保存前不探测摄像头；合法的离线配置仍能成功。

本切片同时实现创建响应所需的共享 Camera 状态聚合和 `CameraDetail` 组装能力。06 复用这些能力
实现详情读取和页面，08 复用状态聚合实现批量列表；05 不提前实现 `GET /cameras`、详情页面、
播放器、编辑、删除或媒体事务补偿，也不新增幂等键、Outbox 或通用 CRUD Service。

新增表单位于现有 `/cameras` 页面。05 只增加“添加 Camera”入口和 Dialog，保留当前列表占位内容；
成功后停留在该页面，不跳转到尚未实现的详情页。正式列表、搜索和 Cards 仍由 08 所有。

## 任务拆分与执行顺序

本切片跨越 Backend 创建事务/媒体投影与 Frontend 动态表单两个可独立验证的运行边界。05.1、05.2
按顺序交付创建功能；功能验收完成后，再执行不改变行为的 Frontend 结构重构：

1. [05.1｜Backend Camera 创建 API](01-backend-camera-create.md)：交付可独立调用和验证的真实
   `POST /api/v1/cameras`，其余 handler 保持占位。
2. [05.2｜Frontend Camera 新增 Dialog](02-frontend-camera-create-dialog.md)：以上一步实际落地的
   HTTP/错误行为为输入，交付 `/cameras` 新增入口、表单交互和前端场景测试。
3. [05.3｜Frontend Camera 目录与创建 Dialog 重构](03-frontend-camera-structure-refactor.md)：保持
   路由、API 和交互不变，把 Camera 业务代码移入 Feature 目录，并拆分过大的创建 Dialog。

05.1、05.2 交付创建行为，05.3 在不改变行为的前提下完成 Frontend 目录和组件重构。共享 Camera
状态投影属于 05.1 创建响应的必要能力，不另拆成只有内部抽象、没有完整对外交付物的任务。

## 请求与响应

```json
{
  "name": "洗手区 01",
  "ip_address": "192.168.1.64",
  "rtsp_port": 554,
  "username": "admin",
  "password": "camera-secret",
  "sources": [
    {
      "name": "主码流",
      "url_suffix": "Streaming/Channels/101",
      "is_default_preview": true
    },
    {
      "name": "子码流",
      "url_suffix": "/Streaming/Channels/102",
      "is_default_preview": false
    }
  ]
}
```

成功返回 `201 CameraDetail`、`Location: /api/v1/cameras/{camera_id}` 和
`Cache-Control: no-store`。`CameraDetail` 的字段形状和敏感数据边界由
[详情](../06-camera-detail/README.md#cameradetail)与
[Foundation](../01-foundation/README.md#敏感数据)所有；创建 Source 不接受 `source_id`，公共字段规则
见 [Foundation](../01-foundation/README.md#领域与字段)。

| 场景           | 字段 / code                                                   |
| -------------- | ------------------------------------------------------------- |
| 无 Source      | `sources/SOURCE_REQUIRED`                                     |
| 无默认源       | `sources/DEFAULT_SOURCE_REQUIRED`                             |
| 多个默认源     | 后续 `sources[i].is_default_preview/MULTIPLE_DEFAULT_SOURCES` |
| 规范化后缀重复 | 后续 `sources[i].url_suffix/DUPLICATE_SOURCE_SUFFIX`          |
| 只读或未知字段 | 对应字段 / `UNKNOWN_FIELD`                                    |

`CameraCreateRequest` 必须继续在 OpenAPI 声明 `sources.minItems=1`，同时为 HTTP 空数组输出上表的
`SOURCE_REQUIRED`，不能让 Pydantic 的列表长度错误变成 `OUT_OF_RANGE`。直接调用 Application/Domain
时仍由 Camera 聚合执行同一业务规则，不能只在 Router 校验。HTTP Schema 保留现有 `min_length=1`，
并在列表长度约束前用不携带输入值的自定义 Pydantic 错误类型标记空数组；公共校验转换器只按该
错误类型输出 `SOURCE_REQUIRED`，不得按字段名或错误文案猜测。

用户输入导致的重复后缀必须在写库前由领域规则返回准确 `422`。数据库已知约束只转换成不包含 SQL、
参数或约束名的应用错误：除非 Application 根据本次请求仍能准确定位字段，否则沿用 Foundation 的
安全服务端错误，不猜测数组下标，也不把所有数据库冲突伪装成字段错误。数据库连接或事务操作失败
返回 `503 DATABASE_UNAVAILABLE`。

## Backend 实施

### 创建用例

新增框架无关的创建 Application Service，并显式注入当前请求的 `CameraUnitOfWork`、共享
`StreamGatewayPort`、`IdGenerator` 和 `Clock`。固定顺序如下：

1. 把请求 Source 按数组顺序转换为领域输入，由 `Camera.create` 完成规范化、不变量校验、Camera 与
   Source UUID v4 生成以及同一 UTC 时间写入。
2. 调用 `uow.cameras.add(camera)` 后显式 `commit`。`add` 或 `commit` 失败时回滚并停止，不能调用
   MediaMTX；任意数据库失败不得留下只有 Camera 或部分 Source 的数据。
3. 提交成功后，复用 04 的 `build_camera_desired_sources`，按 Source 顺序为全部新 Source 各调用一次
   `ensure_path`。只捕获 Port 声明的 MediaMTX 不可用或无效响应并继续其余 Source；不重试、不反向
   修改数据库、不吞掉任务取消。
4. 全部即时同步尝试结束后只获取一次完整 Runtime Path 快照。成功快照或受支持的 Adapter 失败都
   交给 03 的批量投影函数；失败投影使用同一次显式 UTC 完成时间。部分 Path 未就绪按快照正常投影。
5. 使用共享纯函数统计在线数：全部 Source 在线为 `ONLINE`，零路在线为 `OFFLINE`，其余为
   `DEGRADED`；同时返回 `online_source_count` 和配置 `source_count`。函数必须校验投影与聚合的
   Source ID、顺序和数量一致，06、08 和后续响应组装直接复用，Stream Gateway 不实现 Camera 规则。
6. API 映射器按持久化 Source 顺序组装 `CameraDetail`，使用领域能力派生展示用完整 RTSP URL，只为
   严格在线 Source 保留投影中的 `whep_url`。Router 设置 Location 与 no-store 响应头。

数据库一旦提交，随后 MediaMTX 超时、不可用、无效响应或部分 Path 未就绪仍返回 `201` 和确定的
降级投影；后台对账负责最终恢复映射。创建用例不调用 GET 详情 handler，也不把媒体调用放入数据库
事务。

提交后的每个受支持 `ensure_path` 或 Runtime 快照失败各计一次。一次创建请求无论累计多少次失败，
最多输出一条 `camera.media_sync_degraded` WARNING，记录 Camera ID 和失败调用数；Adapter 的单次
诊断保留在 DEBUG。告警不记录 Camera、Source 列表、凭据、URL 或异常文本，trace 由统一 Handler
从当前请求上下文补充。

共享投影放在 Cameras Application：把当前只存在于 API Schema 的 `CameraStatus` 移到该模块，
Schema 直接复用同一枚举，不能复制一套同值类型。纯函数返回包含状态和两个计数的不可变结果；创建
用例返回 Camera、按序 Source 投影和该聚合结果的有类型结果对象，API 层再映射为 Pydantic
`CameraDetail`。这样 06、08 可以复用 Camera 规则，同时 Application 不依赖 FastAPI/Pydantic。

### 依赖、错误与测试替身

- 生产依赖使用现有请求级 UoW 和 lifespan 级 Stream Gateway；生产 UUID/Clock 使用 Foundation 的
  `Uuid4Generator`、`SystemClock`，测试可以替换为固定序列和固定时间。
- 创建 handler 原位替换 Foundation 占位；其余六个 handler 生命周期不变，不能顺带移除占位。
- 领域、持久化、Adapter 错误继续通过现有脱敏异常边界转换；创建服务、响应映射和日志不得记录
  请求 DTO、Camera 聚合、凭据、完整 RTSP URL 或 MediaMTX 原始响应。
- 若客户端在数据库提交后、收到响应前中断，请求结果对客户端属于未知；服务端不为此回滚已提交
  聚合，下一轮媒体对账仍可恢复其 Source。

## Frontend 实施

### Dialog 与字段行为

- `/cameras` 的页面主操作打开 Create Dialog；使用现有 shadcn `Dialog`、`Field`、`Input`、
  `RadioGroup`、`Button`、`ScrollArea`、`Alert`、`Spinner` 和根级 Sonner，不新增 UI primitive。
- 使用现有 React Hook Form 与 Zod。初始值包含一路空 Source 且默认选中，`rtsp_port=554`；用户名和
  密码使用合适的 `autocomplete`，密码输入不在错误或通知中回显。
- Source 新增到末尾且不改变当前默认，顺序固定为添加时的视觉顺序，不提供排序；删除默认源时选择
  删除后剩余数组的第一项；最后一路不可删除。图标按钮均有可访问名称。
- Dialog Body 可滚动、Footer 保持可见。提交期间禁用取消、关闭、增删和再次提交，并保留按钮
  尺寸与可感知的加载文案。
- `422 VALIDATION_ERROR` 使用现有 Problem 字段路径映射到 React Hook Form，保留服务端顺序并聚焦
  第一个可定位字段；无法定位的错误显示在表单级 Alert。失败不清空或关闭表单。

### 成功、确定失败与未知结果

- 成功后关闭并重置 Dialog，显示成功通知，并按前缀失效 `queryKey: ["cameras"]`。不把创建响应
  主动写入详情 Query cache，不跳转详情；响应中的 `whep_url` 仅作为 `CameraDetail` 契约验收，不由
  创建表单启动播放器或循环准备播放。
- 已收到可信 `422` 时属于确定失败，允许用户修正后再次提交。
- `ApiTransportError`、`ApiUnexpectedResponseError` 或可信 `503` 都按“创建结果未知”处理：保留输入，
  显示可能已经创建成功的持久提示，绝不自动重发。用户稍后在 08 提供的列表中核对；05 不使用名称
  或 IP 猜测结果，因为两者都不唯一，也不为解决该场景提前实现列表或新增幂等协议。
- 未知结果提示后，用户若再次点击保存，属于一次明确的新写请求，界面必须提示可能创建重复 Camera；
  不能由 Query/Mutation 的默认重试机制静默发起。
- CameraDetail 和表单草稿只保存在当前页面内存；不得写入 localStorage、IndexedDB、离线缓存或持久化
  Query cache。

## 验收

### Backend

- 单 Source、双 Source、十 Source 创建使用固定 ID/时钟，断言 Source 顺序、连续 `sort_order`、唯一
  默认源、服务端 UUID v4 和相同创建时间。
- 前导 `/` 被移除；空 Source、无默认源、多个默认源、重复后缀、非法 IPv4/端口和未知字段得到上文
  准确字段路径与 code，且 OpenAPI 仍声明 `sources.minItems=1`。
- `add`、flush 或 commit 失败完整回滚且零 MediaMTX 调用；数据库错误、Problem 和日志不含 SQL、
  约束名、测试密码或完整 RTSP URL。
- 提交后按顺序为全部 Source 尽力 `ensure_path`；单项失败继续其余项；运行快照只读取一次，媒体失败
  仍返回 `201`，下一轮对账能够恢复；多个受支持媒体错误只产生一条带 trace 的请求级 WARNING。
- 在线 Path 返回 WHEP URL；离线、缺失、未就绪或 Control API 故障返回确定状态和
  `whep_url=null`。
- 共享纯聚合函数覆盖全在线 `ONLINE`、全离线 `OFFLINE`、混合 `DEGRADED`、计数以及 Source
  ID/顺序/数量不匹配的防御分支。
- API 集成测试断言 `201`、Location、no-store、完整 `CameraDetail`、请求级依赖替换和创建 handler
  已通过对应占位门禁；其他 handler 仍保持占位。

### Frontend

- 初始值、增删、固定添加顺序、默认源重选、最后一路保护、十 Source 和提交期间禁止关闭/重复提交
  均有组件测试。
- 成功关闭并重置 Dialog、显示通知、失效 Cameras 前缀且不跳转；创建响应不进入持久化缓存，也不
  自动启动播放器。
- 嵌套 `422` 映射并聚焦第一个字段；数据库失败保留输入；网络中断、未知响应和 `503` 显示结果未知、
  不自动重发，并在用户明确再次保存前提示重复风险。
- MSW 场景可以分别独立演示成功、字段错误、数据库失败和未知提交结果；可访问名称、焦点和敏感数据
  门禁通过。

### 验证命令

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
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
```

需要 PostgreSQL 的事务验收必须配置独立 `TEST_DATABASE_URL`；相关测试被跳过时，不能宣称数据库
回滚和延迟约束路径已完成验证。05 完成后仍使用 `foundation` 占位门禁，完整 `mvp` 门禁留到 11。
