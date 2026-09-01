# 2026-09-01｜Camera 列表页面

## 变化

- `/cameras` 支持按名称或 IPv4 搜索、上一页/下一页分页、手动刷新失败恢复和进入 Camera 详情。
- `q/page/page_size` 保存在 URL；搜索使用 300ms 防抖和 replace，分页使用正常历史记录。
- 列表明确区分无 Camera、搜索无结果、页码越界、首次失败和后台失败；正常后台刷新不显示提示。
- Camera Card 展示非敏感摘要；详情 Link、详情返回和 Cameras Breadcrumb 保留当前列表参数。
- 通过 shadcn CLI 增加 Pagination，并按项目 Base UI 与 TanStack Router 组合成语义链接。
- 列表页按原型移除额外页面标题、说明和搜索视觉标签，搜索框与添加按钮保持同一行。
- URL 缺少 `page_size` 时按首次视口的 4/2/1 列选择 `12/6/4`；写入 URL 后不再随窗口变化。
- Camera Card 按原型改为整卡详情 Link，使用 16:9 静态媒体区、Source 名称 overlay、Camera 状态、
  地址和在线统计布局；移除媒体区左上角 Source 状态 Badge，实时 video 仍留给后续任务。

## 影响

- Frontend 页面可见时每 15 秒无感刷新列表，页面隐藏时暂停；刷新期间不插入状态行，后台失败不卸载
  已有 Cards，并显示非阻塞错误提示。
- 初始网络失败或可信 `503 DATABASE_UNAVAILABLE` 最多自动重试一次，其他错误不自动重试。
- API、数据库和部署配置无变化。Card 仍为静态摘要，不渲染 video，也不建立 WHEP Session。
- 列表响应、页面文本和 Frontend Query cache 不增加用户名、密码、Source 后缀或 RTSP URL。

## 验证

使用 Camera 合同与敏感数据检查、Frontend Query/路由/组件测试、Lint、格式检查和生产构建验证；同时
检查响应式 Card Grid、键盘 Link 和 URL 前进/后退恢复。

当前规则见 [Camera 列表](../modules/cameras/camera-list.md)。
