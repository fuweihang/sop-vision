# 06.2｜Frontend 只读 Camera 详情页与交付文档

## 任务目标

把现有 `/cameras/$cameraId` 路由接到 06.1 已实现的详情接口，完成可直接访问、可后台刷新、能够正确
处理 404 的只读 Camera 详情页，并完成 06 的最终文档处理。

## 当前上下文与前置条件

- 06.1 必须已经完成。开始前读取其实际 Application、Router、错误处理、API 测试、OpenAPI 和生成
  类型，确认成功与错误行为；不要只依据 06.1 计划假定 Backend 状态。
- Frontend 已有：
  - `getCamera(cameraId, apiClient)` 和 `cameraQueryKeys.camera(cameraId)`；
  - `CameraDetail` 生成类型、Fixture 与 Camera MSW 成功/404 场景；
  - `/cameras/$cameraId` 文件路由、Breadcrumb、返回链接、Pending、Error 和 Not Found 组件；
  - 内存 `QueryClient`，未接入 localStorage 或 IndexedDB persister。
- UI 实施前读取 `docs/design-system/agent-guidelines.md`、`catalog.json`、`page-patterns.md`、布局和交互
  规格，并检查现有 `frontend/src/components/ui/`。不得手动编辑 `frontend/src/routeTree.gen.ts`。
- 当前依赖是 TanStack Router 1.x 与 TanStack Query 5.x。遵循项目已确认模式：loader 使用
  `ensureQueryData`，页面使用同一 Query Options 的 `useSuspenseQuery` 订阅缓存更新。

## 实施范围

### Query 与路由生命周期

- 新增详情 Query Options 工厂，复用 `cameraQueryKeys.camera(cameraId)` 和注入的 Axios Client，不在
  Query 文件创建第二个生产 Client。
- 固定 `staleTime=15s`、`gcTime=5min`、`refetchInterval=15s`、
  `refetchIntervalInBackground=false`。页面可见时后台刷新，隐藏时暂停；后台刷新保留旧内容。
- retry 函数按稳定错误分支处理：可信 404、422、`CAMERA_AGGREGATE_INVALID` 和意外响应不重试；
  网络失败或可信 `DATABASE_UNAVAILABLE` 最多自动重试一次。
- 路由 loader 从 Router Context 取得 `queryClient/apiClient`，通过 Query Options 预取详情。loader 只
  返回 Camera 名称供 Breadcrumb 使用，完整 `CameraDetail` 只放在 Query 内存缓存。
- loader 将可信 `404 CAMERA_NOT_FOUND` 转为 TanStack Router not-found；其他错误继续进入现有
  Cameras Route Error。直接 URL、浏览器刷新和站内进入必须得到相同行为。
- 页面用同一 Query Options 调用 `useSuspenseQuery`，不能只读取 loader 初始值，否则后台刷新不会
  更新页面。

### 只读页面

- Entity Header 展示 Camera 名称和聚合状态，沿用 Shell 已有返回 Cameras 链接；不显示启动预览、
  编辑或删除按钮。
- Connection Information 展示 Camera ID、IPv4、RTSP 端口、用户名、密码、创建时间和更新时间。
- 只读预览区域使用 `AspectRatio` 保留后续播放器位置，只展示默认 Source 的名称、默认标记、状态、
  稳定 error 和最近检查时间；不得创建 `video`、PeerConnection、Playback 请求或恢复控件。
- Camera Sources 按响应顺序展示名称、默认标记、状态、最近检查时间、`url_suffix` 和完整
  `rtsp_url`。
- RTSP URL 使用可换行的等宽普通文本，不渲染为链接，不提供复制按钮、菜单、提示、复制说明或
  Clipboard API 调用。
- 使用现有 `PageContainer`、`PageHeader`、`Card`、`AspectRatio`、`Badge`、`Alert`、`Skeleton` 和
  已有 Shell 组件；不新增 UI primitive，不修改全局主题。
- 首次加载骨架必须匹配本任务只读页面。给现有共享详情骨架增加关闭操作按钮占位的最小参数，Camera
  详情关闭该区域；不得为单一页面复制整套共享骨架。

### 测试与最终文档

- Query 测试覆盖 key、时间参数、隐藏暂停、retry 分类和注入 Client。
- 路由测试覆盖直接 URL、刷新等价行为、Breadcrumb 名称、404 not-found、其他错误、首次 Pending、
  后台刷新保留内容以及卸载后缓存进入回收周期。
- 页面测试覆盖完整配置、默认 Source、Source 顺序、状态/error/时间、RTSP URL 普通文本、窄屏换行、
  Light/Dark、Reduced Motion、键盘和焦点。
- 负向断言页面不存在复制控件、Clipboard 调用、`video`、Playback 请求、编辑、默认源切换和删除操作。
- 保持 CameraDetail 仅在会话内存中；测试结束清空共享 Query cache，敏感 Fixture 不得跨测试保留。
- 完成代码与全套验证后：
  1. 新增 `docs/modules/cameras/camera-detail.md`；
  2. 更新 `docs/modules/cameras/README.md` 和受影响的当前能力说明；
  3. 新增 `docs/changes/` 交付记录；
  4. 把 07 的详情前置链接改为当前能力文档；
  5. 从 `docs/plans/cameras-mvp/README.md` 移除 06，并删除整个 `06-camera-detail/` 目录。

## 明确不做

- 不修改 Backend 业务行为；若发现 06.1 与 OpenAPI 不一致，停止本任务并先修复或重新审核 06.1。
- 不创建播放器、不调用 Playback、不实现 WHEP 恢复或 PeerConnection 生命周期。
- 不实现编辑、默认源切换、删除、列表 Cards 或搜索分页。
- 不提供任何 RTSP URL 复制能力，不把完整详情写入 localStorage、IndexedDB、离线缓存、通知或日志。
- 不新增 UI primitive、全局主题能力、通用详情框架或持久化 Query cache。

## 实施步骤

1. 核对 06.1 实际响应和现有 MSW 场景，先补 Query Options 与 retry 单元测试。
2. 接入 loader、`useSuspenseQuery`、Breadcrumb、404 和错误状态，完成直接 URL 与刷新测试。
3. 实现只读 Header、连接信息、预览状态和 Source 列表，调整详情骨架的最小参数。
4. 补页面行为、无操作控件、敏感数据、响应式和可访问性测试。
5. 运行 Frontend 与跨端门禁；全部通过后更新当前能力、变更记录和计划链接，再移除 06 目录。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh

# backend/：确认 06.1 未被 Frontend 改动破坏
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

需要 PostgreSQL 的 Backend 测试被跳过时不能宣称 06 最终验证完成。

## 完成标准

- 用户可通过直接 URL、浏览器刷新或站内导航打开同一只读详情页，Breadcrumb 使用 Camera 名称。
- 首次 Pending、后台刷新、隐藏暂停、404、其他错误和 retry 次数均有确定测试。
- 页面完整展示连接信息、默认 Source 与按序 Source；RTSP URL 只是普通文本。
- 页面不存在播放器、Playback、复制、编辑、默认源切换或删除行为，敏感数据门禁通过。
- 前后端完整验证通过，当前能力文档和变更记录已增加，父计划与 07 链接已更新，06 计划目录已移除。

## 与 07 的衔接

07 应复用本任务留下的只读预览区域、默认 Source 投影和详情 Query：

- 非空 `whep_url` 由 07 在预览区域内直接建立 WHEP 会话。
- 空 `whep_url` 按稳定 error 决定是否调用 Playback 或提示用户。
- 07 不得重新实现详情读取、Query Key、404 页面或 Connection/Source 信息布局。
