# 04｜媒体 Desired State 对账

> 前置：[Foundation](../01-foundation/README.md)、[Stream Gateway Adapter](../03-stream-gateway-adapter/README.md)
>
> 交付：数据库提交后媒体同步、启动/周期对账和 MediaMTX 重启恢复；无新公共路由

PostgreSQL 保存全部 CameraSource Desired State；MediaMTX Path 是可重建 Runtime State。对账是
MTX 重启和进程崩溃后的主要恢复路径，Playback 只能作为用户需要播放时的第二道自愈防线。

## 即时同步边界

Camera 创建、更新或删除只在 PostgreSQL 成功提交后调用媒体端口：

```text
数据库事务提交
      │
      ├─ 创建：ensure 新 Source Path
      ├─ 更新：ensure 新增/连接变化 Path；release 已删除 Path
      └─ 删除：release 所属全部 Path
```

外部调用不持有数据库事务。调用失败只记录脱敏结果并令本次媒体投影降级，不能返回虚假的数据库
回滚。即时同步减少用户等待恢复的窗口，但不承担崩溃可靠性。

## 后台全量对账

- Backend 启动后执行一次全量对账，之后默认每 `30s` 执行一次；间隔必须可配置。
- 每轮读取 PostgreSQL 当前全部 Source Desired State和 MediaMTX 配置 Path 快照，按 Source ID
  计算缺失、漂移和孤儿集合。
- 受管 Path 的 `source` 或 `sourceOnDemand` 被 Adapter 标记为未知时按漂移处理；非受管 Path 的
  无关配置字段不参与比较，所有权和快照有效性遵循[Adapter 配置快照](../03-stream-gateway-adapter/README.md#完整配置快照)。
- 缺失或漂移 Path 使用当前数据库配置 `ensure_path`；数据库已不存在的受管 UUID Path 使用
  `release_path`。
- 单项失败不阻断其他 Source，但本轮结果必须标为部分失败并在下轮重试。
- Control API 整体不可用时使用有上限、带抖动的退避；恢复后重新获取完整双方快照，不能沿用
  失败前的部分结果。
- 关闭应用时对账任务可取消、限时退出并复用 lifespan 管理的 HTTP Client。

多 worker 或多 Backend 实例不能各自无协调地修改同一 MediaMTX。MVP 使用 PostgreSQL advisory
lock 或等价跨实例租约保证单轮只有一个活动 Reconciler；进程内锁不能承担该职责。

## 并发与所有权

- MediaMTX 实例为 SOP Vision 专用；对账只管理标准 UUID v4 名称的 Path。
- 即时同步与后台对账都发送从 PostgreSQL 最新数据构造的幂等 Desired State。
- Playback 与删除并发时，Playback 必须先确认 Source 当前仍存在；删除提交后的下轮对账最终
  清除晚到请求留下的孤儿 Path。
- 更新与 Playback 并发时不比较前端版本；最终 Path 必须收敛到数据库中最后提交的配置。
- 对账不把凭据、完整期望配置或远端配置写入日志、指标标签、追踪或持久化缓存。

## 健康与验收

- MediaMTX 停机不令 Camera 配置读写整体失去 Backend readiness；媒体健康单独观测。
- 覆盖 MTX 重启后全量恢复、单 Path 漂移、缺失 Path、孤儿 Path、部分失败和下一轮成功。
- 覆盖两个 Reconciler 竞争、即时同步与周期对账交错、Playback 与删除并发。
- 证明进程在数据库提交后、媒体调用前崩溃时，后续对账仍能恢复 Desired State。
- 证明清理失败不会复活数据库 Camera，恢复失败也不会删除合法数据库配置。
