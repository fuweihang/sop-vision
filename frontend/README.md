# SOP Vision Frontend

Frontend 使用 React 19、TypeScript、Vite、TanStack Router/Query、Tailwind CSS v4 和 shadcn/ui。
当前已完成应用 Shell、主题、路由状态、生成式 API Client、错误映射、Cameras MSW 和 Camera 新增
Dialog；Cameras 列表/详情与 Detection Tasks 页面仍是业务骨架。

## 环境与启动

要求 Node.js 24 和 pnpm 11。在 `frontend/` 目录执行：

```bash
corepack enable
pnpm install --frozen-lockfile
cp .env.local.example .env.local
pnpm dev
```

开发服务器固定监听 <http://127.0.0.1:8000>。默认 API 地址为
`http://127.0.0.1:3001/api/v1`，可通过 `VITE_API_BASE_URL` 覆盖。

## 当前页面

| 路由                 | 当前实现                                          |
| -------------------- | ------------------------------------------------- |
| `/`                  | 重定向到 `/cameras`                               |
| `/cameras`           | App Shell、Camera 新增 Dialog、路由状态和列表骨架 |
| `/cameras/$cameraId` | 详情层级、Breadcrumb、返回操作和详情骨架          |
| `/tasks`             | App Shell、标题和列表骨架                         |
| `/tasks/$taskId`     | 详情层级、Breadcrumb、返回操作和详情骨架          |

Shell 已支持桌面 Sidebar、移动 Sheet、Light/Dark 主题、跳转主内容、路由后焦点恢复和响应式
重排。页面文档中的表单、列表数据、播放器、ROI 和任务操作属于后续业务实现。

## API 与生成文件

- `src/lib/api-client.ts` 是唯一 Axios 实例和错误入口。
- `src/features/cameras/api/cameras-api.ts` 封装六个已冻结的目标 operation。
- `src/generated/openapi.ts` 从 `contracts/openapi.json` 生成，不得手工修改。
- `src/routeTree.gen.ts` 由 TanStack Router 插件生成，不得手工修改。
- `CameraDetail` 含凭据，只能短期保存在内存；不得进入浏览器持久化存储或错误上报。

重新生成 OpenAPI 类型：

```bash
pnpm api:generate
```

跨端修改应从仓库根目录运行 `bash scripts/check-cameras-contracts.sh`，保证 Backend OpenAPI 与
Frontend 类型同步。

## Cameras MSW 场景

后端业务 handler 尚未实现时，可在 Vite 开发模式显式启用一个场景：

```dotenv
VITE_API_MOCK_SCENARIO=success
```

| 场景                         | 行为                            |
| ---------------------------- | ------------------------------- |
| `success`                    | 六个 Cameras operation 全部成功 |
| `empty-list`                 | 列表没有 Camera                 |
| `search-no-results`          | 搜索没有匹配项                  |
| `nested-validation-error`    | 创建和更新返回嵌套字段 `422`    |
| `camera-not-found`           | 返回 `404`                      |
| `dependency-unavailable`     | 返回 `503`                      |
| `initial-failure`            | 列表首次失败、重试成功          |
| `background-refresh-failure` | 首次成功、后台刷新失败          |

Mock 仅在开发模式且变量非空时启动。无效场景或未处理请求会直接失败，不会透传到真实网络。
生产构建不会注册 MSW Worker。

## 目录约定

```text
frontend/src/
├── components/
│   ├── app-shell/        # 全局 Shell、导航、Header 和焦点管理
│   ├── layout/           # 页面布局组合
│   ├── page-state/       # 数据页面 Empty/Error/Refresh 状态
│   ├── route-state/      # Router Pending/Error/Not Found 状态
│   └── ui/               # shadcn primitive
├── features/
│   └── cameras/          # Camera API、Query Key、表单规则和业务组件
├── generated/            # OpenAPI 生成类型
├── lib/                  # Router、Query Client、Axios Client 和共享逻辑
├── mocks/                # 类型安全 Fixture 与 MSW 场景
├── providers/            # Theme、Query 与全局 UI Provider
└── routes/               # TanStack Router 文件路由
```

共享 UI 变更前先阅读 [Design System](../docs/design-system/README.md)。Route 配置和轻量页面入口使用
`routes/`，跨业务复用组件放入根 `components/`，业务专属代码放入 `features/<domain>/`；不要编辑
生成文件。

## 质量检查

```bash
pnpm test
pnpm test:sensitive-data
pnpm lint
pnpm format:check
pnpm build
```

`pnpm build` 同时执行 TypeScript project build 和 Vite 生产构建。修复格式或 Lint 时分别使用
`pnpm format`、`pnpm lint:fix`。
