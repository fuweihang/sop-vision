# 05.3｜Frontend Camera 目录与创建 Dialog 重构

> 状态：已完成
>
> 父方案：[05｜创建 Camera](README.md)
>
> 前置任务：[05.2｜Frontend Camera 新增 Dialog](02-frontend-camera-create-dialog.md)

## 任务目标

在不改变 Camera 创建 API、路由、页面布局、表单行为和错误处理的前提下，明确 Frontend 的 Route、
项目级共享组件和 Camera 业务代码边界。把 Camera 专属 API、Query Key、表单和组件集中到
`features/cameras/`，并拆分当前过大的 Create Dialog，降低 06 详情、08 列表和 09 编辑继续开发时的
修改冲突。

本任务只做代码组织和组件拆分。创建功能已经由 05.2 验收完成，根 Cameras MVP 状态继续保持
“创建已完成”；执行本任务时不得借重构改变已经通过测试的业务行为。

## 当前判断

- 现有 TanStack Router 目录符合文件路由约定：`_app/route.tsx` 是无 URL 段的 Layout，
  `cameras/route.tsx` 是父 Route，`cameras/index.tsx` 是索引页面，`$cameraId.tsx` 是动态详情 Route。
- `vite.config.ts` 已启用 `autoCodeSplitting: true`。Route 文件中直接定义未导出的页面组件是正常用法，
  不需要为了拆包改成 `.lazy.tsx`。
- 当前 Route 文件只有 Route 配置、Router Hook 和轻量页面组合，不存在必须整体迁出 `routes/` 的复杂
  页面。`routes/` 中出现 TSX 不是本次问题来源。
- 根 `components/` 目前同时包含项目级共享组件和 Camera 专属组件；Camera API、Query Key 又位于
  通用 `lib/`。继续增加列表、详情和编辑后，业务文件会分散在多个通用目录。
- `camera-create-dialog.tsx` 当前同时处理 Dialog 生命周期、React Hook Form、Source 数组、Mutation、
  服务端错误映射和全部字段 JSX，文件明显大于其他业务组件，应按稳定职责拆分。

## 目录规则

### `routes/`

保留以下内容：

- `createFileRoute`、`validateSearch`、`beforeLoad`、`loader` 和 `staticData`。
- Params、Search、Loader Data 和 Router Context 的读取。
- `pendingComponent`、`errorComponent`、`notFoundComponent` 和轻量页面入口。
- 只服务于当前 Route、且足够短小的 Layout 或页面组合。

Route 文件中直接定义的组件不得导出，以保持自动拆包行为。未来页面变复杂并移入 Feature 后，Route
文件保留一个小型 Adapter：读取 Router 数据，再通过 props 传给 Feature Page。Feature 不得反向导入
Route 文件中的 `Route`，避免循环依赖和拆包边界不清。

`routes/` 下若必须共置非路由文件或测试，使用默认的 `-` 前缀让 Router 插件忽略；不得手工修改
`routeTree.gen.ts`。本项目已经启用自动拆包，本任务不新增 `.lazy.tsx`。

### 根 `components/`

只保存跨业务或项目级复用的 React 组件：

- `ui/`：shadcn primitive。
- `app-shell/`：全局 Shell、导航和 Header。
- `layout/`：跨页面布局组合。
- `page-state/`：共享数据页面状态。
- `route-state/`：共享 Router 状态。

Camera、Task 等只属于一个业务域的组件放入各自 Feature，不因为文件是 TSX 就放入根
`components/`。页面入口也不以“是否为组件”为标准迁出 `routes/`，而以复杂度和职责判断。

### `features/cameras/`

集中保存 Camera 专属 API、缓存身份、表单规则和业务组件。通用 Axios Client、Problem 解析、Query
Client、Router 和 OpenAPI 生成类型继续保留在 `lib/` 或 `generated/`。

## 目标目录

```text
frontend/src/
├── routes/
│   └── _app/
│       └── cameras/
│           ├── route.tsx
│           ├── index.tsx
│           └── $cameraId.tsx
├── features/
│   └── cameras/
│       ├── api/
│       │   ├── cameras-api.ts
│       │   ├── cameras-api.test.ts
│       │   ├── camera-query-keys.ts
│       │   └── camera-query-keys.test.ts
│       ├── forms/
│       │   ├── camera-create-form.ts
│       │   ├── camera-create-form.test.ts
│       │   ├── camera-create-error-mapping.ts
│       │   └── camera-create-error-mapping.test.ts
│       └── components/
│           ├── camera-create-dialog.tsx
│           ├── camera-create-dialog.test.tsx
│           ├── camera-create-connection-fields.tsx
│           └── camera-create-source-fields.tsx
├── components/
│   ├── ui/
│   ├── app-shell/
│   ├── layout/
│   ├── page-state/
│   └── route-state/
└── lib/
    ├── api-client.ts
    ├── api-errors.ts
    ├── query-client.ts
    └── router.ts
```

本任务不创建 `features/cameras/pages/`。当前 Cameras 列表和详情仍是短小路由骨架，正式页面分别由
08 和 06 实现；届时只有页面已经包含查询、筛选或多个业务 Section 时，才增加 Feature Page。

## 文件调整

| 当前文件                                             | 目标文件或处理方式                                                |
| ---------------------------------------------------- | ----------------------------------------------------------------- |
| `lib/cameras-api.ts` 及测试                          | 移到 `features/cameras/api/`，保持七个 operation 和类型不变       |
| `lib/camera-query-keys.ts` 及测试                    | 移到 `features/cameras/api/`，保持现有三个 Key 工厂及形状不变     |
| `components/cameras/camera-create-form.ts` 及测试    | 移到 `features/cameras/forms/`，继续保存 Schema、默认值和请求转换 |
| `components/cameras/camera-create-dialog.tsx` 及测试 | 移到 `features/cameras/components/` 后按下文拆分                  |
| `routes/_app/cameras/index.tsx`                      | 保留 Route 和当前轻量 `CamerasPage`，只更新 Dialog import         |
| `mocks/cameras/*`                                    | 继续留在集中式 MSW 目录，只更新 Camera API 类型 import            |
| `components/page-state/*`                            | 继续作为共享组件，只更新 Camera API 与 Query Key import           |

移动文件时同步更新 `frontend/README.md` 的目录说明和 API 文件位置。不要新增 barrel `index.ts`；调用方
继续从明确文件导入，避免隐藏依赖和形成新的循环引用。

## Dialog 拆分

### `camera-create-dialog.tsx`

保留：

- Dialog 的 open/reset/提交锁定生命周期。
- React Hook Form 和 `useFieldArray` 的唯一所有权。
- Create Mutation、Query 前缀失效、Sonner 成功反馈。
- 成功、确定失败和未知结果的状态切换。
- Header、滚动 Body、Footer 和两个字段组件的组合。

不要把 Form Provider、Mutation 或 Dialog open 状态扩散成全局 Store，也不要为一次创建流程增加通用
表单框架。

### `camera-create-connection-fields.tsx`

只渲染 `name/ip_address/rtsp_port/username/password`，通过明确 props 接收 `formId`、React Hook Form
注册能力、错误和 disabled 状态。密码的 autocomplete、脱敏和不 trim 规则保持不变。

### `camera-create-source-fields.tsx`

只渲染 Source FieldSet、RadioGroup 和增删操作。父 Dialog 继续拥有 Field Array，子组件不得复制
一份 Source 状态。以下行为必须保持：新增项追加到末尾、其余项顺序固定、最后一路不可删除、删除
默认项后选择第一项、提交期间全部禁用、图标按钮有可访问名称。

### `camera-create-error-mapping.ts`

保存不依赖 React 渲染的错误判断和字段路径转换，包括 Backend Problem 路径到 React Hook Form 字段
的安全映射、确定失败 Alert 和结果未知 Alert。未知异常仍重新抛出，不能把程序错误伪装成用户可修复
错误；错误对象和提示不得携带密码、完整 RTSP URL、Axios Request 或原始响应。

## 实施步骤

1. 在改动前运行现有 Camera 表单、路由、API、Query Key 和敏感数据测试，记录基线；若基线失败，先
   判断是否为已有问题，不在重构中顺带改变断言。
2. 创建 `features/cameras/api`、`forms` 和 `components`，先机械移动 Camera API、Query Key、表单及其
   测试，更新 Route、MSW、共享页面状态和测试中的全部 import；此步不修改函数签名或 Query Key。
3. 把字段路径识别、Alert 构造和可纯测的错误分类移到 `camera-create-error-mapping.ts`，补充独立单元
   测试后再从 Dialog 接入。
4. 抽出 Connection Fields 和 Source Fields。保持 React Hook Form、Field Array 和 Mutation 仍由
   Dialog 统一拥有，避免为了拆文件引入双向 ref、Context 或跨文件可变状态。
5. 检查 `/cameras` Route 仍只负责 Router Context 读取和页面组合；不移动当前列表骨架，不改变
   `createFileRoute("/_app/cameras/")`，不新增 Route 或 `.lazy.tsx`。
6. 更新 `frontend/README.md` 目录树和 Camera API 位置，说明根 `components/`、`features/`、`routes/`
   的边界；设计系统规则没有变化时不修改 `docs/design-system/`。
7. 运行全部 Frontend、契约和敏感数据检查。只有行为测试、类型检查、Lint、格式和生产 Build 全部通过
   后，才把本文件状态改为已完成，并把父方案状态恢复为无待执行项。

## 明确不做

- 不改变 `/cameras` URL、Route ID、Breadcrumb、Pending/Error/Not Found 或自动拆包配置。
- 不实现 06 Camera 详情、08 Camera 列表、09 编辑或任何播放器功能。
- 不改变 OpenAPI、请求/响应字段、Query Key 形状、Mutation 重试、缓存写入和失效范围。
- 不改变 Dialog 文案、布局、shadcn primitive、键盘/焦点行为、Source 规则或提交状态。
- 不引入新的状态管理、表单、拖拽或目录生成依赖。
- 不编辑 `routeTree.gen.ts`，不把测试或辅助文件误生成为 Route。
- 不降低凭据、完整 RTSP URL、Mutation Cache 和未知提交结果的安全要求。

## 验证方式

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
bash scripts/check-cameras-sensitive-data.sh
git diff --check

# frontend/
pnpm test
pnpm test:sensitive-data
pnpm lint
pnpm format:check
pnpm build
```

还要执行以下结构与行为检查：

- `rg` 不再找到指向 `@/lib/cameras-api`、`@/lib/camera-query-keys` 或
  `@/components/cameras` 的旧 import。
- 生产 Build 成功生成原有 Route Tree，`/cameras`、`/cameras/$cameraId`、`/tasks` 和
  `/tasks/$taskId` 均保持可访问，没有新增意外路由。
- Create Dialog 原有组件测试继续覆盖初始值、十 Source、增删与固定顺序、唯一默认源、提交锁定、成功、
  嵌套 422、数据库失败、网络中断、未知响应和可信 503。
- DOM、通知、错误、测试输出、Query/Mutation Cache 和持久化存储仍不泄漏测试密码或完整 RTSP URL。
- Dialog 主文件不再同时包含全部字段 JSX 和全部错误路径映射；拆分后的组件仍由一个 Form 和一个
  Field Array 驱动，没有重复业务状态。

## 完成标准

- Camera 专属 API、Query Key、表单和业务组件集中在 `features/cameras/`；根 `components/` 和 `lib/`
  只保留项目级共享能力。
- TanStack Router 目录、Route ID、URL 和自动拆包方式保持不变；Route 文件继续承担轻量入口职责。
- Create Dialog 已按连接字段、Source 字段和错误映射拆分，创建行为及安全边界没有变化。
- Frontend 全量测试、敏感数据测试、Lint、格式、Build、跨端契约和敏感数据脚本全部通过。
- 本文件和父方案状态已更新，06–11 的实现状态没有被本次纯重构提前改变。
