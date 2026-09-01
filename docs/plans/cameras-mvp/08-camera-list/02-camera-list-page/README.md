# 02｜Camera 列表页面

## 任务目标

把 `/cameras` 从路由骨架实现为可搜索、分页、刷新和进入详情的资源列表。查询状态由 URL 恢复，页面
明确区分首次加载、空数据、搜索无结果、后台刷新和可恢复失败。本阶段交付静态 Camera Cards，不建立
任何 WHEP Session。

## 当前上下文与前置条件

- [01｜Camera 列表 API](../01-camera-list-api/README.md)必须已经实施完成并通过验证。
- 开始实施前以当前 `contracts/openapi.json`、生成类型、`listCameras` Client、Query Key、Fixture 和
  MSW handler 为准，不使用 01 计划中的旧假设代替实际代码。
- 先阅读 [Cameras 基础能力](../../../../modules/cameras/foundation.md)和设计系统中的
  [Page Patterns](../../../../design-system/specs/page-patterns.md)、
  [Interaction and Accessibility](../../../../design-system/specs/interaction-accessibility.md)及
  `layout.yaml`。
- 当前 `/cameras` 已有 `PageHeader`、创建入口和路由级 Card Skeleton；`PageEmptyState`、
  `PageRecoverableError`、`PageBackgroundStatus` 等共享状态组件已经存在，应优先复用。
- 项目使用 TanStack Router、TanStack Query 和 Zod 4。Route search 类型必须由 `validateSearch` 推断，
  不使用 cast，也不手工编辑 `routeTree.gen.ts`。

## 实施范围

### URL 与数据查询

- `/cameras` 的 URL 保存 `q/page/page_size`。`validateSearch` 将缺失或非法值分别恢复为
  `q=undefined`、`page=1`、`page_size=20`，同时遵守 Backend 的 q 长度和分页上限。
- `loaderDeps` 只选择校验后的 `q/page/page_size`；loader、Query Key、页面订阅和分页控件复用同一个
  规范化结果，不能形成两个参数默认值来源。
- loader 使用 Router Context 中的 `apiClient/queryClient` 预取，页面使用同一 Query Options 订阅。
- 首次加载使用现有 Card Skeleton；页面可见时每 15 秒刷新，页面隐藏时暂停，后台刷新保留旧 Cards。
- 初始网络失败或可信 `503 DATABASE_UNAVAILABLE` 最多自动重试一次。`422`、
  `500 CAMERA_AGGREGATE_INVALID`、非法响应和程序错误不自动重试。

### 搜索与分页

- 搜索输入显示当前 q，用户输入后防抖 300ms 更新 URL，同时把 page 重置为 1。
- 防抖产生的 URL 更新使用 `replace`，避免每个输入字符新增浏览器历史记录；分页导航正常新增历史，
  浏览器前进/后退可以恢复原查询。
- 清除搜索立即恢复无 q 的第一页。组件卸载或外部 URL 改变时取消过期防抖，不能让旧输入覆盖新的
  Router 状态。
- 分页使用 API 返回的 `page/page_size/total` 计算可用操作；越界空页保持真实页码与 total，不自行
  篡改 API 响应或隐式跳转。

### 页面与静态 Cards

- `total=0` 且无 q 时显示“尚无摄像头”和创建入口；存在 q 时显示“未找到匹配摄像头”、清除操作，
  两者使用不同的稳定页面状态。
- 非空结果使用设计系统的响应式 Resource Card Grid：宽屏 4 列、中等 2 列、紧凑视口 1 列，不产生
  页面级水平滚动。
- 每张静态 Card 只展示列表已有的 Camera 名称、IPv4/端口、Camera 状态、默认 Source 名称和在线计数，
  并提供语义明确、可键盘访问且有 Focus Visible 的详情 Link。
- Card 不展示用户名、密码、Source 后缀、RTSP URL、告警或 Detection 模拟数据。
- 初始失败使用可恢复错误状态；后台刷新中和刷新失败使用非阻塞状态，不卸载旧 Cards。
- 创建成功继续按公共缓存矩阵失效 `cameras`，当前页面应自动读取新列表数据。

## 明确不做

- 不渲染 video、`VideoSurface`、LIVE overlay，也不调用 `useStreamSession`。
- 不添加 IntersectionObserver、页面隐藏释放 Lease 或共享 Session 测试；这些由 03 负责。
- 不修改 Backend 列表业务规则、响应字段或媒体状态聚合。
- 不实现列表内编辑、删除、切换默认源、排序、过滤器或批量操作。

## 实施步骤

1. 新增列表 Query Options 和重试策略，确保 loader 与页面订阅复用相同 Key、Client、刷新周期及内存
   cache 设置。
2. 为 `/cameras` 增加 Zod 4 `validateSearch`、最小 `loaderDeps` 和 loader 预取；保持类型完全推断。
3. 实现搜索输入与 300ms 防抖 URL 同步，处理 q 变化重置 page、replace 历史、清除操作、URL 外部变化
   和卸载清理。
4. 实现分页模型和可访问控件；所有 Link/navigation 均携带完整且已经校验的 search 状态。
5. 用现有 Page State 和设计系统 Grid 实现空数据、无结果、初始错误、后台刷新及静态 Camera Cards。
6. 扩展 MSW 场景和 Fixture，覆盖多页、越界、搜索、初始失败、后台失败和聚合损坏，所有未知请求仍
   直接失败。
7. 增加 Query、Route 和组件测试，更新生成路由树的正常构建产物；不要手工编辑生成文件。
8. 更新 Cameras 当前能力文档和阶段变更记录，明确列表浏览已可用但 Card 实时预览等待 03。不要提前
   移除整个 08 计划。

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
```

另外使用浏览器或 Playwright 检查 1440px、约 900px 和紧凑视口：无全局水平滚动，键盘可以完成搜索、
分页、清除和进入详情，浏览器前进/后退能恢复列表状态。

## 完成标准

- 直接访问、刷新及浏览器前进/后退都能从 URL 恢复 q、page 和 page_size。
- 缺失或非法 search 值稳定恢复默认值；Backend 的非法分页 `422` 测试仍独立存在。
- 搜索防抖、page 重置、replace 历史和过期更新清理通过确定性测试。
- 首次加载、空数据、无结果、初始失败、后台刷新和后台失败分别呈现正确状态。
- 非空列表可以分页浏览并通过语义 Link 进入对应详情；响应式布局和键盘焦点符合设计系统。
- 页面没有 WHEP reader、Stream Session 或 video DOM；敏感数据检查通过。
- Frontend 测试、Lint、格式和生产构建全部通过。

## 与下一任务的衔接

下一步执行 [03｜Camera Card 预览](../03-camera-card-preview/README.md)。03 在本任务稳定的 Card 数据、
Grid、Query 刷新和路由卸载行为上增加媒体预览，不再修改搜索、分页或页面状态规则。
