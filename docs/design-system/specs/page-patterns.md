# Page Patterns

页面模式定义组件如何组合。Agent 应先选择最接近的模式，再填充业务内容，而不是从空白画布开始。

## 1. Workspace Overview

适用于项目总览、运营状态和资源入口。

```text
┌──────── Sidebar ────────┬──────────── Header ──────────────┐
│ Team / Search           │ Scope       Breadcrumb     Agent │
│ Primary navigation      ├───────────────────────────────────┤
│                         │ Search / View / Primary action    │
│                         ├──────────────┬────────────────────┤
│                         │ Usage/Alerts │ Projects/Resources │
│ Account                 │ Recent items │                    │
└─────────────────────────┴──────────────┴────────────────────┘
```

规则：

- 全局搜索和主要创建操作位于内容顶部。
- 信息摘要位于左列，主要实体位于更宽的右列。
- 没有数据时保持卡片结构，使用 Empty State，不改变页面骨架。
- 一页只设置一个视觉最强的主操作。

## 2. Data List With Filters

适用于部署、日志、告警和检测记录。

结构顺序：

1. Shell Header。
2. Filter Bar。
3. 结果摘要或批量操作区。
4. Table/List/Grid。
5. Pagination 或增量加载状态。

规则：

- Filter Bar 使用 36px 高控件和 8px 间距，可换行但不能横向溢出。
- 多选筛选器显示已选数量，例如 `6/7`。
- 空结果必须区分“系统没有数据”和“筛选条件没有匹配”。
- 表格列密度遵循 14px 正文，状态使用 Badge，不用整行高饱和底色。
- 筛选条件宜同步到 URL，便于 Agent、用户和测试复现状态。

## 3. Settings Card Stack

适用于团队配置、系统参数和账号设置。

```text
Secondary navigation |  Card: title + description + field
                     |  Footer: help text          Save
                     |
                     |  Card: title + description + controls
                     |  Footer: documentation      Save
```

规则：

- 内容区域使用约 914px 最大宽度，卡片间距 32px。
- 每张卡片只表达一个设置主题。
- 标题与说明放在 Card Body，帮助文本与提交按钮放在 Footer。
- Save 默认不可用，只有值发生有效变化后启用。
- 危险操作放在页面末尾，与常规设置保持明显空间分隔。
- 禁用控件必须解释原因或提供升级/权限路径。

## 4. Empty State

适用于尚未创建资源、无匹配结果、不可用或无权限状态。

内容模板：

```text
[icon]
具体、简短的状态标题
解释原因或下一步的单句说明
[optional action]
```

禁止使用泛化文案，如“暂无数据”，而不说明数据类型或下一步。

## 5. Detail Page

适用于一次检测、一次部署、一个项目或一个工单。

- Header 显示实体名称、状态和最重要操作。
- 首屏展示摘要、当前状态和关键异常。
- 次级信息使用 Tabs 或连续 sections，避免多层嵌套卡片。
- 原始日志、ID、时间和机器数据使用等宽字体与可复制操作。
- 破坏性操作只出现在相关设置区域，不放在主信息流中。

## AI Design 输出要求

为新页面给出：所选模式、主要 section、复用组件、所需新 token、各状态、1280×720 首屏行为和窄屏降级方案。没有这些信息的视觉稿不应直接进入编码。

## AI Coding 输出要求

实现必须标明使用了哪些语义 token 和组件规格。新组件只有在现有组件无法表达需求时创建，并需要同步补充 `components.yaml` 和视觉回归用例。

