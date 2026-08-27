# 05.2｜Frontend Camera 新增 Dialog

> 状态：待实施
>
> 父方案：[05｜创建 Camera](README.md)
>
> 前置任务：[05.1｜Backend Camera 创建 API](01-backend-camera-create.md)

## 任务目标

在现有 `/cameras` 页面增加“添加 Camera”主操作和可访问的新增 Dialog，让用户编辑 Camera 连接信息、
动态 Source 数组和唯一默认源，并正确处理成功、字段错误、数据库失败与提交结果未知。该任务完成后，
05 创建切片作为跨端功能整体完成；正式列表、详情和播放仍由后续切片实现。

## 当前上下文与前置条件

新会话开始时必须先完整读取父方案、前置任务最终文档和 diff、`docs/cameras-mvp/AGENTS.md`、
Foundation Frontend 契约、`docs/design-system/` 规则及当前 Frontend 代码。必须确认 05.1 已实际完成并
通过 Backend 验证，不能只根据本文件假设接口行为。

当前基础包括：

- `/cameras` 文件路由和 App Shell 已存在，页面正文仍是列表占位；05 只能替换标题区和新增入口所需
  组合，不能实现 08 的列表、搜索或 Cards。
- shadcn `Dialog`、`Field`、`Input`、`RadioGroup`、`Button`、`ScrollArea`、`Alert`、`Spinner` 和根级
  Sonner 已安装，不需要新增 primitive。
- React Hook Form、Zod、TanStack Query、Axios Client、OpenAPI 生成类型、`createCamera`、Problem
  映射、Camera Query Key 和 MSW Cameras 场景已存在。
- CameraDetail 含凭据与完整 RTSP URL，只允许当前会话内存短期存在；不得主动写入详情 Query cache
  或持久化存储。
- Camera 名称和 IP 均不唯一。网络中断、未知响应或可信 `503` 后无法由 Frontend 判断是否已经创建，
  必须按结果未知处理，不能自动重复 POST。

该项目存在 `components.json`，实现时使用仓库 `shadcn` 技能核对现有组件用法；React Hook Form、Zod、
TanStack Query 或 Router API 用法按仓库规则通过 Context7 查询当前文档。因为不新增 primitive，不运行
shadcn add 命令。

## 实施范围

### 表单与 Dialog

- 在 `/cameras` 页面标题区增加唯一主操作“添加 Camera”，打开受控 Create Dialog；列表占位正文继续
  保留，成功后不跳转详情。
- 使用 React Hook Form 与 Zod 管理字段。初始值为 `rtsp_port=554`，以及一路名称/后缀为空且已选为
  默认源的 Source。
- Camera 字段包括 `name/ip_address/rtsp_port/username/password`；每路 Source 包括
  `name/url_suffix/is_default_preview`，请求中不得加入 `source_id`。
- Source 新增到末尾且不改变已有默认项；最后一路不可删除；删除默认项后选择剩余数组第一项。
- 使用上移/下移按钮调整数组顺序，不引入拖拽库。按钮按边界禁用，全部图标按钮有可访问名称。
- 默认源使用 `RadioGroup` 表达唯一选择；重排不能改变默认 Source 身份。
- Body 使用有界滚动区域，Footer 始终可见。提交中禁用关闭、取消、字段修改、增删、排序与重复提交；
  加载状态保持按钮尺寸并提供可感知文本。
- Label、描述、字段错误与控件按现有 `Field` 组合；密码使用 password input 和合适 autocomplete，任何
  Alert、Sonner、测试失败信息都不能回显凭据。

### 提交状态与错误映射

- 使用 `createCamera` 和 TanStack Query mutation，明确设置写请求不自动重试。
- 成功后关闭并重置 Dialog、显示成功通知、以前缀 `queryKey: ["cameras"]` 失效查询；不写入
  `["camera", cameraId]`，不启动播放器、不调用 Playback、不跳转详情。
- 可信 `422 VALIDATION_ERROR` 使用现有 Problem 字段路径映射到 React Hook Form，保持后端错误顺序，
  设置字段错误后聚焦第一个当前存在且可聚焦的控件。无法定位的字段错误显示为表单级 Alert。
- `ApiTransportError`、`ApiUnexpectedResponseError` 和可信 `503` 统一进入“创建结果未知”：保留全部输入，
  显示可能已成功的持久 Alert，不关闭 Dialog、不自动查询占位列表、不自动再次 POST。
- 结果未知后允许用户发起一次明确的新保存，但在请求前必须持续提示可能创建重复 Camera；不能把
  名称或 IP 当作唯一键，也不在本任务增加幂等协议。
- 其他可信确定错误按稳定 `status/code` 展示恢复建议；Frontend 不比较 `title/detail` 决定业务分支。

### MSW、测试与状态文档

- 保持 Cameras MSW 工厂为每个场景返回七条目标 operation handler，未知请求继续失败。
- 复用现有 success、nested-validation-error、dependency-unavailable，并增加或用局部测试 handler
  明确覆盖网络失败和无法识别响应；场景必须相互隔离、计数器不能跨测试泄漏。
- 增加表单数据操作、Dialog、mutation 状态、字段聚焦、可访问性和敏感数据组件测试。
- 完成全部跨端验证后，把本任务和父方案状态改为已完成，并把根 Cameras MVP 状态表的 05 改为
  已完成；06–11 保持原状态。

## 明确不做

- 不实现 Camera 列表请求、搜索、分页、Cards、后台刷新或空列表状态；这些属于 08。
- 不实现详情 loader/页面、编辑、默认源切换、删除、播放器或 Playback 恢复。
- 不新增路由，不跳转 `/cameras/{camera_id}`，不把创建响应塞入尚未使用的详情缓存。
- 不新增 UI primitive、拖拽依赖、全局表单框架或通用动态数组抽象。
- 不把表单草稿、CameraDetail、密码或 RTSP URL 写入 localStorage、IndexedDB、离线缓存或持久化
  Query cache。
- 不根据名称/IP 猜测未知提交是否成功，不隐藏 `503` 的结果不确定性，不自动重发写请求。

## 实施步骤

1. 核对 05.1 的真实 OpenAPI、Frontend 生成类型和 `createCamera` 错误行为；若契约已改变，先使用项目
   命令重新生成类型，不能手改生成文件。
2. 阅读设计系统 Camera Form Dialog、Field、loading/error 和布局规则，核对现有组件公共 API。
3. 实现表单值 Schema、默认值和 Source 数组操作的纯辅助逻辑，先覆盖增删、排序和默认源身份测试。
4. 组合 Create Dialog，完成可访问标签、滚动 Body、固定 Footer 和提交中锁定行为。
5. 接入 mutation，分别实现成功、可信 422、结果未知和其他确定错误分支，关闭默认写重试。
6. 把主操作接入 `/cameras` 页面，同时保留属于 08 的列表占位正文。
7. 补充 MSW/局部失败 handler、组件测试、敏感数据与路由回归测试。
8. 运行全部 Frontend、跨端契约和敏感数据门禁；通过后再更新 05 与根状态文档。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# frontend/
pnpm test
pnpm lint
pnpm format:check
pnpm build

# backend/：确认前置接口没有被跨端生成或 Fixture 修改破坏
uv run --env-file .env.local pytest
uv run python scripts/check_camera_placeholders.py foundation
```

还要执行以下组件行为检查：

- 打开时为端口 554、一路默认 Source；新增、上移、下移和删除保持顺序及唯一默认源。
- 最后一路不可删除；删除默认项选择剩余第一项；十路 Source 仍可在有界 Body 中操作。
- 提交期间 Escape、外部点击、取消、关闭、编辑、增删排序和再次保存均不起作用。
- 成功后 Dialog 重置并关闭、显示通知、仅失效 Cameras 前缀且当前路由仍为 `/cameras`。
- 嵌套 `422` 聚焦第一个可定位错误；未知字段路径进入表单级错误且输入保留。
- 网络失败、未知响应和 `503` 均显示结果未知且请求次数保持一次；用户明确再次保存前可看到重复风险。
- DOM、通知、错误、测试输出和持久化存储中没有测试密码或完整 RTSP URL 泄漏。

## 完成标准

- 用户可以在 `/cameras` 打开 Dialog，创建单路或多路 Source Camera，并看到明确成功反馈。
- 所有 Source 数组与默认源规则、提交锁定、字段聚焦和未知结果行为均有组件测试。
- Frontend 没有实现列表/详情/播放等后续职责，也没有引入新 primitive 或拖拽依赖。
- Frontend 全量测试、Lint、格式、Build、Backend 回归、契约和敏感数据脚本全部通过。
- 父方案与根状态表的 05 已更新为已完成，06–11 状态未改变。

## 与下一任务的衔接

05.2 是创建切片最后一个任务。完成后，06 可直接复用 05.1 提供的 Camera 状态聚合与
`CameraDetail` 映射实现 GET 详情；08 可在 `/cameras` 当前页面保留新增入口并替换列表占位正文。

交接时必须记录：实际执行的验证命令、是否跳过 PostgreSQL 集成测试、可见 UI 变更，以及任何未完成
验收。不得把 06 或 08 的待办留在 05 状态中并仍标记 05 已完成。
