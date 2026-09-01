# 日志事件与级别

> 输出格式、配置和安全规则见 [Backend 日志](README.md)。业务触发条件仍由对应模块文档负责。

## 组件名

Formatter 按最长 Logger 段前缀选择 `component`。未命中的 `app.*` Logger 去掉 `app.`，其他 Logger
保留完整名称。

| Logger 或前缀                                    | component              |
| ------------------------------------------------ | ---------------------- |
| root                                             | `backend`              |
| `app.factory`                                    | `backend.lifecycle`    |
| `app.modules.stream_gateway.services.mediamtx`   | `stream.gateway`       |
| `app.modules.cameras.application.reconciliation` | `media.reconciliation` |
| `app.modules.cameras.application.listing`        | `camera.list`          |
| `app.modules.cameras.application.detail`         | `camera.detail`        |
| `app.modules.cameras.application.create`         | `camera.create`        |
| `app.modules.cameras.persistence.integrity`      | `camera.integrity`     |
| `app.core.http.access`                           | `http.access`          |
| `uvicorn`、`uvicorn.error`                       | `server`               |
| `sqlalchemy.engine`                              | `database.sql`         |
| `alembic`                                        | `database.migration`   |

`uvicorn.access` 对应的 `server.access` 只为兼容映射保留；Runtime 已关闭 Uvicorn 原生 access log。

## 已注册事件

表中字段顺序也是 console 展示顺序。事件不得附加表外字段；Formatter 不会展开未知 `extra`。

| event                                  | component              | 级别规则                                                   | 允许字段                                                                                                                           |
| -------------------------------------- | ---------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `stream_gateway.io`                    | `stream.gateway`       | 始终 DEBUG                                                 | `operation,outcome,duration_ms`；失败加 `error_type`；单 Source 操作加 `source_id`；成功快照加 `path_count`                        |
| `media_reconciliation.round_completed` | `media.reconciliation` | 无变更或锁竞争 DEBUG；有 ensure/release INFO               | `outcome`；成功加 `desired_count,managed_path_count`；有变更再加 `ensured_count,released_count`；最后加 `duration_ms`              |
| `media_reconciliation.round_failed`    | `media.reconciliation` | 首次、结果变化或 30 分钟提醒 WARNING；其余持续故障 DEBUG   | `outcome`；仅部分失败加五个计数字段；再加 `retry_in_seconds,consecutive_failures,degraded_duration_seconds,duration_ms`            |
| `media_reconciliation.recovered`       | `media.reconciliation` | INFO                                                       | `outcome,desired_count,managed_path_count,ensured_count,released_count,consecutive_failures,degraded_duration_seconds,duration_ms` |
| `media_reconciliation.runner_exit`     | `backend.lifecycle`    | ERROR                                                      | `outcome,timeout_seconds,error_type,error_frames`                                                                                  |
| `camera.media_sync_degraded`           | `camera.create`        | WARNING                                                    | `operation,outcome,camera_id,failed_count`                                                                                         |
| `camera.detail_aggregate_invalid`      | `camera.detail`        | ERROR                                                      | `operation,outcome,camera_id`                                                                                                      |
| `camera.list_aggregate_invalid`        | `camera.list`          | ERROR                                                      | `operation,outcome`                                                                                                                |
| `camera.reference_integrity_failed`    | `camera.integrity`     | ERROR                                                      | `integrity_issue_kind,camera_id,source_id`                                                                                         |
| `http.request_completed`               | `http.access`          | 完整 100–499 为 INFO；完整 500–599、处理失败或中断为 ERROR | `method,path,status_code,outcome,duration_ms`                                                                                      |

媒体对账的失败、恢复和计数取舍见
[媒体对账](../cameras/media-reconciliation.md#日志与安全)；Camera 创建提交后的媒体降级规则见
[Camera 创建](../cameras/camera-create.md#创建用例)。

## 字段类型

- `event`、`trace_id`、`operation`、`outcome`、`error_type`、各类 ID、method 和 path 使用非空字符串。
- `error_frames` 使用字符串数组。
- `duration_ms`、`status_code` 和全部 count 使用非负整数，布尔值不作为整数接受。
- `retry_in_seconds`、`degraded_duration_seconds`、`timeout_seconds` 使用有限非负数值。
- UUID 和 Enum 在写入 LogRecord 前转换为稳定字符串。

JSON 使用完整字段名和数值类型。console 使用以下短键和单位：

| JSON 字段                                   | console                   |
| ------------------------------------------- | ------------------------- |
| `outcome`                                   | `result`                  |
| `duration_ms`                               | `duration=<n>ms`          |
| `error_type/error_frames`                   | `error/frames`            |
| `camera_id/source_id`                       | `camera/source`           |
| `path_count`                                | `paths`                   |
| `desired_count/managed_path_count`          | `desired/managed`         |
| `ensured_count/released_count/failed_count` | `ensured/released/failed` |
| `retry_in_seconds/consecutive_failures`     | `retry=<n.n>s/failures`   |
| `degraded_duration_seconds`                 | `degraded=<n.n>s`         |
| `integrity_issue_kind`                      | `kind`                    |
| `status_code`                               | `status`                  |
| `timeout_seconds`                           | `timeout=<n.n>s`          |
| `trace_id`                                  | `trace`                   |

console 不显示 `event` 和完整 Logger 名；需要按事件检索或告警时必须使用 JSON。

## Logger 级别

| Logger                            | 级别                                                   |
| --------------------------------- | ------------------------------------------------------ |
| root                              | 固定 WARNING，阻止未登记第三方 DEBUG/INFO 噪声         |
| `app`、`uvicorn`、`uvicorn.error` | 跟随 `BACKEND_LOG_LEVEL`                               |
| `uvicorn.access`                  | CRITICAL 且不传播；Uvicorn 同时设置 `access_log=False` |
| `httpx`、`httpcore`               | 固定 WARNING，避免请求细节随 Backend DEBUG 输出        |
| `sqlalchemy`                      | 固定 WARNING                                           |
| `sqlalchemy.engine`               | `DATABASE_ECHO=true` 时 INFO，否则 WARNING             |
| `alembic`                         | INFO；迁移嵌入其他进程时保留宿主 Handler               |

所有 Runtime 记录进入同一个 level=`NOTSET` 的 stderr Handler，最终是否产生记录由 Logger 级别决定。
已列 Logger 不保留自己的输出 Handler，避免重复打印。
