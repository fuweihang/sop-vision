# SOP Vision 产品范围

本文描述仍有效的产品方向，不代表所有能力已经实现。当前实现状态以
[文档入口](README.md) 为准；Camera 第一阶段的精确契约以
[Cameras 当前能力](modules/cameras/README.md)和
[Cameras MVP 剩余计划](plans/cameras-mvp/README.md)为准。

## 产品定位

SOP Vision 是企业内部视觉检测平台，围绕两类核心资源工作：

1. 物理 Camera 及其多路 RTSP CameraSource。
2. 绑定一路 CameraSource 和一套 Algorithm 的 Detection Task。

“SOP”是产品定位，当前没有定义多步骤流程编排引擎。

## 当前交付边界

已交付的是工程运行栈、Backend/Frontend 公共基础、Cameras Foundation、MediaMTX Adapter 和
后台媒体对账。数据库中已有 Camera Source 时，Backend 能在启动及周期轮询中恢复 MediaMTX Path
并清理受管孤儿 Path；用户已经可以创建、搜索、分页浏览和完整编辑 Camera，通过 Card 预览并切换
默认 Source，也能在详情自动选择可播放 Source、临时切源和使用自定义播放器。Camera 删除以及
Detection Task 的创建和运行仍未实现；`/tasks` 只用于验证 App Shell 和页面层级。

## Cameras 第一阶段

Cameras MVP 已提供创建、搜索分页列表、Card 实时预览、详情、配置更新、默认源切换和详情 WHEP
播放，剩余计划继续提供删除和发布验收。第一阶段完整范围包括：

- 按名称或 IPv4 搜索、分页浏览 Camera。
- 查看完整配置、Source 状态和默认 Source。
- 完整更新 Camera 与 Source 集合，或独立切换默认预览源。
- 更新提交后把最新 Source Desired State 同步到 MediaMTX，并从 MediaMTX 获取运行状态。
- 列表和详情直接使用 Backend 返回的在线 WHEP 地址预览；同一 Source 共享一个 WHEP Session 和
  MediaStream，Card 与 Detail 使用各自的 video DOM 和业务 overlay。
- 详情使用无原生 controls 的实时播放器，提供开始/停止、播放/暂停、临时 Source 切换、静音/音量、
  网页全屏、浏览器全屏、LIVE、连接状态和重连；实时 WHEP 不提供进度、seek、快进或快退。
- 二次确认后删除 Camera，并在数据库提交后尽力释放媒体映射；周期对账恢复 MTX 重启后的
  合法 Path 并清理受管孤儿 Path。

本阶段明确不包含 Camera 启停、厂商字段、批量操作、保存前连通性探测、录像、截图、回放、
Detection WebSocket、检测 Canvas 与帧同步、WebRTC 质量统计、软删除、跨业务删除保护和事务级
Outbox/Saga 媒体投递。周期 Desired State
对账属于 MVP，但不提供与数据库同事务、零窗口或恰好一次的外部副作用保证。完整字段与错误语义
不在本文重复，当前行为见 [Cameras 模块文档](modules/cameras/README.md)，目标行为见
[Cameras MVP 剩余计划](plans/cameras-mvp/README.md)。

## Detection Tasks 目标范围

Detection Tasks 尚未实现，以下内容是后续产品基线，而不是已冻结 API。

### 业务对象

Detection Task 至少需要：

- 稳定 `task_id`、名称和可选描述。
- 一个稳定 `source_id`，不得用数组下标引用 CameraSource。
- 一个稳定 `algorithm_id` 及由 Algorithm schema 驱动的参数。
- Algorithm 要求时保存 ROI。
- `enabled` 表示期望运行状态；Actual State 单独维护。
- 配置版本和已应用版本，用于表达“已保存但尚未生效”。

同一路 CameraSource 可以被多个任务选择。是否复用连接、解码或帧数据属于 Detector 技术设计，
不由产品关系直接决定。

### 计划用户能力

- 搜索和浏览任务列表，区分无任务与搜索无结果。
- 创建、查看、编辑和删除任务。
- 选择 CameraSource 和 Algorithm，按 schema 填写参数并绘制 ROI。
- 启动、停止、重载和重启任务，并看到操作中的忙碌、成功和失败状态。
- 查看绑定信息、实时画面、检测 overlay、ROI、运行状态和错误。实时画面复用 Cameras 阶段的
  `VideoSurface`；检测结果通过独立 Canvas 绘制，不重绘视频。

新任务保存后默认停止。编辑已存在任务不得隐式改变 `enabled`；“保存配置”和“把配置应用到
运行实例”必须有清晰、可观测的边界。任务没有暂停状态。

### 状态原则

`enabled` 不能代替 Actual State。例如 `enabled=true` 仍可能处于启动中、重连、降级或错误。
正式状态枚举、转换条件、超时、重试和按钮可用性尚未冻结，应随 Detector 控制协议一起定义。

## 共同体验要求

- 桌面使用 Sidebar，紧凑视口使用 Sheet；当前路由通过 Breadcrumb 和返回操作表达层级。
- 首次加载、后台刷新、空数据、搜索无结果和可恢复失败是不同状态。
- 状态不能只用颜色表达；关键操作具有明确文字、可访问名称和键盘焦点。
- 耗时操作保持控件尺寸、阻止重复提交，并提供恢复动作。
- 不可逆删除使用明确对象名称和后果的二次确认。
- 视频由 `<video>` 渲染；普通业务信息使用 HTML overlay，检测框、Keypoint、Track 和 ROI 使用独立
  Canvas，不复制全部视频帧。

组件、布局与交互细节见 [Design System](design-system/README.md)。

## 当前范围外

- 历史检测结果、异常证据、证据视频和回放。
- 检测测试工具、图片/视频上传测试和模型评测。
- 多步骤 SOP 编排。
- 多租户、组织、用户、鉴权、RBAC 和审计。
- 多 Worker 调度、GPU 负载均衡和自动故障转移。
- 录像存储、告警渠道和业务报表。

范围外不等于永久不做；在契约和验收未冻结前，UI 不应展示不可用入口。

## 仍需冻结的决策

后续开发前真正需要解决的问题：

1. 用户、角色、可信网络边界，以及 Camera 凭据的加密、展示和轮换策略。
2. Algorithm registry、参数 schema、ROI 类型、坐标约定和版本兼容。
3. Detection Task Actual State 状态机及 start/stop/reload/restart 的超时、幂等和失败恢复。
4. 运行中任务删除语义，以及 CameraSource 被任务引用时的修改/删除保护。
5. 配置版本、已应用版本与 Detector Last Known Good 的生成和对账方式。
6. 实时检测消息协议、发布频率、延迟目标、断线重连和过期判定。
7. Camera/任务/并发流规模、浏览器支持范围及部署网络容量。
8. 历史事件、证据、审计与数据保留策略是否进入后续版本。

## 原型边界

[静态交互原型](prototype/v1.0.html) 是早期布局和业务流程证据。原型中的模拟数据、固定延时、
Hash 路由、数组下标关联、直接凭据展示和前端状态模拟都不是生产实现。React 组件、路由、
可访问性和 API 以当前源码及 Design System 为准。
