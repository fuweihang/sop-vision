# 03｜Camera 列表

> 前置：[Cameras 基础契约](../01-foundation/README.md)  
> 交付：`GET /cameras`、卡片列表、搜索、分页和空状态

## 1. 完成目标

用户可以分页浏览 Camera 卡片，按名称或 IP 搜索，并从卡片进入详情。配置数据始终可读；Source 状态或播放服务不可用时使用降级字段，不让整个列表失败。

## 2. 范围

### 后端

- 分页读取 Camera 摘要和 Source 数量。
- 按名称或 IP 搜索，按白名单字段排序。
- 通过一次 MediaMTX `/paths/list` 快照批量合并 Source 状态和默认源播放投影。
- 对状态或播放依赖执行可读性降级，避免逐行外部调用。

### 前端

- 卡片网格、搜索框、分页和进入详情操作。
- 区分首次加载、后台刷新、无 Camera 和搜索无结果。
- 展示默认源预览区域、聚合状态和在线 Source 数。
- 使用 Fixture 时可独立完成全部列表交互。

### 不属于本模块

- Camera 创建、编辑或删除操作的实现。
- Source 状态判定和播放器内部实现。
- 在列表内展开完整 Camera 详情。

## 3. API

```http
GET /api/v1/cameras?q=洗手&page=1&page_size=20&sort=name
```

成功：

```json
{
  "items": [
    {
      "camera_id": "6f9619ff-8b86-4e4f-9f68-bb3f8f6f4f21",
      "name": "洗手区 01",
      "ip_address": "192.168.1.64",
      "rtsp_port": 554,
      "status": "ONLINE",
      "online_source_count": 2,
      "source_count": 2,
      "default_preview_source": {
        "source_id": "8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d",
        "name": "通道 1 主码流",
        "status": "ONLINE",
        "last_checked_at": "2026-08-19T03:00:00Z",
        "whep_url": "https://vision.example.internal/media/8f14e45f-ea9d-4a7d-9b6d-8c9f0a1b2c3d/whep"
      },
      "created_at": "2026-08-01T03:00:00Z",
      "updated_at": "2026-08-18T06:20:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

列表响应不得包含 `username/password/url_suffix/rtsp_url`。

## 4. 查询语义

- `q` trim 后对 Camera `name` 和规范化 IPv4 文本执行不区分大小写的包含匹配。
- `q` 为空或仅空白时等同未提供。
- 先应用搜索，再计算 `total`，最后排序和分页。
- 相同排序值使用 `camera_id` 升序作为稳定次排序。
- 请求页码超过最后一页时返回空 `items` 和真实 `total`，不自动修改页码。
- 排序白名单为 `name/-name/created_at/-created_at`。

## 5. 状态和播放降级

- `online_source_count` 只统计当前为 `ONLINE` 的 Source。
- Source 对应 Path 名称存在且 `available === true && online === true` 时为 `ONLINE`；否则为 `OFFLINE`。
- 全部 Source 在线时 Camera 为 `ONLINE`，全部离线时为 `OFFLINE`，混合时为 `DEGRADED`。
- `/paths/list` 请求失败或响应无效时，当前页全部 Source 为 `OFFLINE`，Camera 配置和分页仍返回 `200`。
- 默认源播放地址未准备好或 MediaMTX 不可用时，`whep_url=null`。
- 状态或播放字段降级时仍返回 `200`，配置字段和分页结果不得缺失。
- 批量读取状态必须按当前页 Source ID 一次完成，不得对每张卡片发起独立网络请求。

状态聚合的准确规则由 [Source 状态](../07-source-status/README.md) 所有；播放器生命周期由 [Source 预览](../08-source-preview/README.md) 所有。

## 6. 前端卡片契约

每张卡片至少包含：

- 默认源预览区域或明确占位状态。
- Camera 名称和 `IP:端口`。
- `ONLINE/OFFLINE/DEGRADED` 聚合状态。
- 在线 Source 数/总 Source 数。
- 点击卡片进入 `/cameras/{camera_id}`。

交互规则：

- 页面操作栏包含占满剩余宽度的搜索框和“添加摄像头”按钮。
- 搜索输入防抖 `300ms`；改变搜索条件后页码重置为 `1`。
- URL 查询参数保存 `q/page/page_size/sort`，刷新和前进后退可以恢复。
- `total=0` 且无 `q` 时展示“暂无摄像头”和创建入口。
- `total=0` 且存在 `q` 时展示“未找到匹配结果”和清除搜索操作。
- 首次加载使用骨架；后台刷新保留旧卡片并显示非阻塞刷新状态。
- 卡片预览仅在进入可见区域后创建，离开可见区域时释放。
- `whep_url=null` 时显示“预览未就绪”，不得尝试创建播放器。

## 7. 缓存

Query Key：

```text
["cameras", {q, page, page_size, sort}]
```

- 参数必须先规范化再生成 Query Key，避免空字符串和未提供形成两个缓存项。
- 列表数据可短期保存在内存查询缓存，但不得持久化到 localStorage/IndexedDB。
- 创建、更新、默认源切换和删除成功后失效所有 `cameras` 前缀查询。
- 状态轮询只更新状态相关字段，不覆盖仍在后台刷新的配置字段。

## 8. 错误与恢复

| 场景 | 响应/前端行为 |
| --- | --- |
| 非法页码、page size 或 sort | `422 VALIDATION_ERROR`；保留当前可见列表 |
| PostgreSQL 不可用 | `503 DATABASE_UNAVAILABLE`；显示整页重试 |
| MediaMTX Control API 不可用 | `200`，当前页 Source 均为 `OFFLINE` |
| MediaMTX 不可用 | `200`，`whep_url=null` |
| 后台刷新失败 | 保留旧内容并提供非阻塞重试 |

## 9. Fixture

至少提供：

- 空列表、搜索无结果、单卡片、多页数据。
- 三种 Camera 聚合状态。
- 默认源在线、离线、未知和 `whep_url=null`。
- 首次加载失败、后台刷新失败和非法查询参数。
- 固定 25 条 Camera 数据用于分页与稳定排序测试。

Source 状态和播放器在本模块使用 Fake 组件，不要求真实 RTSP 或 MediaMTX。

## 10. 独立验收

1. 默认参数返回第一页 20 条并按名称稳定排序。
2. 名称和 IP 搜索正确，空搜索等同未提供。
3. 无数据和搜索无结果使用不同界面与操作。
4. 非法分页和排序返回准确字段错误。
5. MediaMTX Control API 不可用时，配置列表仍返回 `200` 且 Source 均为 `OFFLINE`。
6. 卡片不泄露用户名、密码、URL 后缀或 RTSP URL。
7. 搜索、分页和排序可由 URL 恢复。
8. 不可见卡片不保留播放器会话。

## 11. Definition of Done

- 列表 API 的查询、分页、稳定排序和批量投影已实现并测试。
- 卡片网格、搜索、分页、空状态、加载和刷新体验已完成。
- 可使用 Mock 数据独立演示所有状态。
- OpenAPI 与前端列表类型契约一致。
