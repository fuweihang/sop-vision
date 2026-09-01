# Camera 列表 API

> 相关文档：[Cameras 基础能力](foundation.md)、[Stream Gateway](stream-gateway.md)、
> [Camera 详情](camera-detail.md)

## 职责与边界

`GET /api/v1/cameras` 返回可供列表页面使用的非敏感 Camera 摘要。接口支持名称或 IPv4 字面包含
搜索，并按 `created_at ASC, camera_id ASC` 稳定分页。当前只完成 Backend API、OpenAPI、Frontend
生成类型和 MSW 场景；列表页面和 Camera Card 播放仍未实现。

列表响应只包含 Camera ID、名称、IPv4、RTSP 端口、聚合状态、Source 计数、默认 Source 摘要和创建/
更新时间。不会返回用户名、密码、Source 后缀、完整 RTSP URL或完整 Source 数组。

## 查询参数

| 参数        | 默认值 | 规则                                      |
| ----------- | ------ | ----------------------------------------- |
| `q`         | 无     | trim 后最长 100 字符；空白等同未提供      |
| `page`      | `1`    | 大于等于 1                               |
| `page_size` | `20`   | 1–100                                    |

搜索对 Camera 名称和 IPv4 不区分大小写。`%`、`_` 和 `\` 按普通字符匹配，不作为 SQL 通配符；额外
查询参数会被忽略。越界页返回空 `items` 和真实 `total`。

## Backend 行为

列表用例在同一个请求级 Unit of Work 中先 count，再读取当前页完整聚合。两次数据库查询后显式
rollback 结束只读事务，之后才访问 MediaMTX，避免等待外部网络时继续占用 PostgreSQL 事务。

- 空页直接返回，不读取 MediaMTX。
- 非空页把当前页全部 Source 合并为一批，只读取一次 Runtime Path 快照。
- MediaMTX 不可用或响应无效时仍返回 `200`；当前页所有 Source 使用同一个失败时间和对应离线错误。
- 只有严格在线的默认 Source 返回 `whep_url`，离线默认 Source 不会改用其他 Source 的播放地址。
- 列表不会创建、修复或释放 MediaMTX Path。
- 当前页任一持久化聚合损坏时返回脱敏的 `500 CAMERA_AGGREGATE_INVALID`，不返回部分结果，也不
  访问 MediaMTX。错误和日志不包含损坏 Camera 的 ID、字段、凭据或 Source 后缀。
- 数据库查询或结束事务失败时返回 `503 DATABASE_UNAVAILABLE`；非法查询参数返回 `422`。

成功响应不设置 `Cache-Control: no-store`，但 Frontend 只能把结果保存在当前会话的内存 Query
cache 中，不得写入持久化浏览器存储。

## 日志与排查

持久化聚合损坏记录 `camera.list_aggregate_invalid`，组件为 `camera.list`、级别为 ERROR，只允许
`operation` 和 `outcome` 字段。数据库 503 先检查 PostgreSQL；接口正常返回但状态全部离线时检查
MediaMTX Control API，不要把媒体降级误判为配置读取失败。

## 验证命令

```bash
# 仓库根目录
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

PostgreSQL 集成测试需要独立 `TEST_DATABASE_URL`；相关测试被跳过时不能算作完整持久化验收。

