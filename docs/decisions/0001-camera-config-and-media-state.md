# 0001｜Camera 配置与媒体运行态分离

## 背景

Camera 配置需要长期保存并支持事务，而 MediaMTX 的 Control API 修改内存配置，重启后可能丢失。
如果把两者伪装成同一个事务，数据库提交成功后的网络超时会让调用方无法判断配置是否已经保存，
也无法真正回滚已经发生的外部媒体操作。

## 决定

- PostgreSQL 是 Camera 和 CameraSource Desired State 的唯一事实源。
- MediaMTX 只保存可丢失、可重建的媒体配置与运行状态。
- Camera 写操作先提交数据库，再尽力同步 MediaMTX；媒体失败返回降级投影，不撤销已提交配置。
- Backend 启动后立即对账并周期执行，用 PostgreSQL 恢复缺失或漂移的 Path，清理受管孤儿 Path。
- 当前不引入跨系统事务、Outbox 或 Saga，也不把 MediaMTX Control API 暴露给 Frontend。

## 影响

- 配置 API 在 MediaMTX 故障时仍可用，但短时间内可能返回 `OFFLINE` 或 `DEGRADED`。
- MediaMTX 重启不会造成配置数据丢失，对账会重新建立 Path。
- 客户端不能把“媒体已在线”作为“配置写入成功”的前提或结果。
- 新的 Camera 写用例必须复用共享 Desired State 构造和 Stream Gateway Port。

当前操作规则见 [Cameras 模块](../modules/cameras/README.md)和
[媒体对账](../modules/cameras/media-reconciliation.md)。

## 调整条件

当业务需要严格的跨系统投递保证、对账窗口无法满足恢复时限，或 MediaMTX 不再是可重建运行态时，
重新评估 Outbox、持久化命令队列或其他交付机制。评估前不得把外部 I/O 放进数据库事务来模拟原子性。
