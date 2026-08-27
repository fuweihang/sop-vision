# 01｜Cameras Foundation

> 状态：已完成。本文记录当前稳定存在的公共能力与后续切片必须遵守的约束。

Foundation 已建立 Camera 领域、关系库持久化、事务、HTTP、跨端类型、Mock 与质量门禁。本文只
维护这些跨切片公共约束；MediaMTX Adapter、后台对账和后续业务页面由各自文档负责。

## 已实现能力

- PostgreSQL async Runtime、独立 Session factory、Alembic revision 链和测试数据库隔离。
- 无外键的 `cameras` / `camera_sources` 模型、稳定约束、完整性巡检和聚合级 Repository/UoW。
- 框架无关的不可变 Camera 聚合、值规则、固定 ID/时钟和 Fake 持久化实现。
- Trace ID、Problem Details、严格 UUID、分页参数、异常脱敏和 OpenAPI 公共响应。
- Cameras 请求/响应 Schema、七个目标占位 Router 和确定性 OpenAPI 导出。
- Frontend 生成类型、单一 API Client、Problem 映射、Query Key、Fixture 和显式 MSW 场景。
- 契约漂移、占位生命周期、迁移/Repository 和敏感数据的自动化门禁。

## 分层边界

```text
HTTP Schema / dependency
          │
          ▼
Cameras application ports
          │
          ▼
     Cameras domain
          ▲
          │
SQLAlchemy repository / UoW

OpenAPI → generated frontend types → Client / MSW
```

- `app/modules/cameras` 拥有 Camera 聚合、持久化端口/适配器和 Cameras HTTP Schema。
- `app/modules/stream_gateway` 只拥有 MediaMTX 运行时能力，不拥有 Camera 配置。
- `app/core/database` 与 `app/core/http` 只提供跨模块基础设施。
- ORM Row 不进入领域/Application 层；领域对象不依赖 FastAPI、Pydantic 或 SQLAlchemy。
- 不建立 Generic Repository、全能 Base Service 或只服务占位阶段的抽象。

## 领域与字段

| 字段                        | 规则                                                                    |
| --------------------------- | ----------------------------------------------------------------------- |
| `camera_id/source_id`       | 服务端生成 UUID v4，全局唯一，创建后不变                                |
| `name`                      | trim 后 `1–128` 字符                                                    |
| `ip_address`                | IPv4                                                                    |
| `rtsp_port`                 | `1–65535`，创建默认 `554`                                               |
| `username/password`         | 分别 `1–128`、`1–512` 字符，不自动 trim                                 |
| `default_preview_source_id` | 必须属于当前 Camera                                                     |
| `url_suffix`                | trim、移除全部前导 `/`，结果 `1–1024` 字符；大小写、查询串和尾 `/` 保留 |
| `sort_order`                | 请求数组顺序，从 `0` 开始连续                                           |
| `created_at/updated_at`     | 服务端生成的带时区 UTC 时间                                             |

Camera 至少包含一路 Source，且恰好一路默认。规范化后缀在同一 Camera 内大小写敏感唯一。
已有 Source 更新时保留 `source_id/created_at`；新增项生成新 ID。持久化数据违反聚合不变量时
抛出损坏错误，不静默修复或返回部分数据。

完整 RTSP URL 按以下语义派生，不单独持久化：

```text
rtsp://{username}:{password}@{ip_address}:{rtsp_port}/{url_suffix}
```

公共字段错误 code 包括 `REQUIRED`、`STRING_TOO_LONG`、`INVALID_IP_ADDRESS`、
`INVALID_UUID`、`OUT_OF_RANGE` 和 `UNKNOWN_FIELD`。聚合和所有权错误由对应功能契约定义。

## 持久化与事务

PostgreSQL 使用原生 `uuid`、`inet` 和 `timestamptz`。两个 Camera 表不建立外键；数据库负责
主键、IPv4、端口、非负顺序，以及同 Camera 后缀/顺序的延迟唯一约束。

跨表不变量由 Camera 专用 Repository/UoW 维护：

- 既有聚合写入先锁 Camera，再按 `source_id` 锁全部 Source。
- `add/save/delete` 只 flush；Application Service 显式 `commit/rollback`。
- 创建、完整更新和删除在一个事务内完成；删除先显式删 Source，再删 Camera。
- 数据库提交后才能更新或释放 MediaMTX 映射；外部失败不能伪装成数据库回滚。
- 完整性巡检检测孤儿 Source、缺失/跨 Camera 默认源和无 Source Camera，只告警不修复。

公共端口是 `CameraRepository.add/save/get/list/count/delete` 与
`CameraUnitOfWork.commit/rollback`。列表搜索对名称和 IPv4 做大小写无关的字面包含匹配；
`%`、`_`、`\` 不作为 SQL 通配符。结果按 `created_at ASC, camera_id ASC` 分页，越界页返回空集。

## HTTP 契约

- API 前缀 `/api/v1`；JSON 字段使用 `snake_case`，枚举使用大写英文值。
- UUID 路径和字段只接受小写、带连字符、RFC variant 正确的 UUID v4 文本。
- 每条路由使用显式、全局唯一的 `operation_id`。
- Playback 占位契约是 `POST /camera-sources/{source_id}/playback`
  （`prepareCameraSourcePlayback`）；该命令可能收敛 MediaMTX Path，不能声明为安全读取。
- 成功响应为 `application/json`；结构化错误为 `application/problem+json`。
- 列表参数：`page >= 1`，`1 <= page_size <= 100`，`q` trim 后最长 100，空白等同未提供。
- 额外查询参数被忽略；请求 DTO 的未知字段返回 `422 UNKNOWN_FIELD`。
- 成功和错误响应均带 `X-Trace-Id`；Problem body 使用同一 `trace_id`。

Problem 的稳定分支字段是 `status/code/errors/context`。Frontend 不比较可变的 `title/detail`：

```json
{
  "type": "urn:sop-vision:problem:validation-error",
  "title": "请求字段验证失败",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "存在一个或者多个无效字段。",
  "instance": "/api/v1/cameras",
  "trace_id": "tr_...",
  "errors": [
    { "field": "sources[0].name", "code": "REQUIRED", "detail": "..." }
  ],
  "context": {}
}
```

| HTTP  | 公共用途                             |
| ----- | ------------------------------------ |
| `400` | 请求整体语义无效                     |
| `404` | Camera 或 Source 不存在              |
| `409` | 播放尚不可用                         |
| `422` | 路径、查询或请求字段错误             |
| `500` | 持久化聚合损坏等服务端不变量错误     |
| `502` | MediaMTX 响应无效                    |
| `503` | 当前请求必需的数据库或媒体依赖不可用 |

框架校验不公开 Pydantic 原始 input；数据库错误不公开 SQL、参数或约束名。只有应用能准确定位
字段时，后缀唯一冲突才转换为 `DUPLICATE_SOURCE_SUFFIX`。

## 敏感数据

- `CameraDetail` 是唯一返回 `username/password/rtsp_url` 的公共形状，成功响应必须
  `Cache-Control: no-store`。
- 列表、Playback、Problem、日志、指标、追踪和错误上报不得包含凭据或完整 RTSP URL。
- Secret、ORM 和领域对象的默认 `repr/str` 不得输出密码。
- `CameraDetail` 只在当前浏览器会话内存中短期保存，不进入 localStorage、IndexedDB、离线
  缓存或持久化 Query cache。

这些边界只能降低泄漏风险；当前没有鉴权、字段加密或 Secret 管理，不能据此认定适合生产暴露。

## Frontend 公共契约

Query Key 固定为：

```text
["cameras", {q, page, page_size}]
["camera", cameraId]
["playback", sourceId]
```

| 变更       | 更新或失效                                                  |
| ---------- | ----------------------------------------------------------- |
| 创建       | `cameras`                                                   |
| 更新       | `cameras`、当前 `camera`、受连接变化或删除影响的 `playback` |
| 切换默认源 | `cameras`、当前 `camera`                                    |
| 删除       | `cameras`、当前 `camera`、所属 Source 的 `playback`         |
| 状态刷新   | 只合并 `cameras/camera` 的状态字段                          |

首次加载、后台刷新、空数据、搜索无结果和可恢复失败必须分开；后台刷新保留旧内容。页面 URL
负责恢复列表查询或详情定位。MSW 只在 Vite 开发模式显式启用，未知场景或未处理请求直接失败。

## 生成与验证

Foundation 的长期门禁：

```bash
# 仓库根目录
bash scripts/check-cameras-contracts.sh
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

`foundation` 占位门禁允许后续切片逐个用完整实现原位替换，但拒绝混入临时代码的半占位。
最终 MVP 必须改用 `mvp` 模式并保证零占位。数据库集成测试需要独立的 `TEST_DATABASE_URL`；
未配置时测试会跳过，不能算作完整持久化验收。
