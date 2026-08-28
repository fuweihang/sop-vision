# 0002｜Backend 使用统一结构化日志与安全输出边界

## 背景

Backend 原先由应用、Uvicorn、SQLAlchemy 和 Alembic 各自格式化日志。业务字段同时出现在 message
和 `extra` 中，缺失字段用 `-` 占位，同一次 MediaMTX 故障由多个层级重复告警。Uvicorn request line
还可能包含 query，SQLAlchemy echo 可能与 root Handler 重复输出并带来参数泄漏风险。

如果把 console 整行文本当作采集接口，人读文案、字段顺序和显示样式都很难继续调整；如果在请求
开始时就记录“成功”或预测状态，也会让中断和流式响应的排障结果失真。

## 决定

- 所有 Runtime Logger 使用一个标准库 logging 配置和一个 stderr Handler。业务代码只创建一条
  LogRecord，console 与 JSON 从同一记录生成。
- console 面向人工阅读，不承诺整行解析兼容；机器采集使用 JSON 的稳定 `event` 和白名单字段。
- 应用级 HTTP access log 在响应完成或中断后记录最多一条，状态码表示实际发送结果；异常详情由
  独立错误日志负责。
- trace 由 Handler Filter 从请求上下文补充。Formatter 只输出登记字段，并把第三方异常压缩为异常
  类型和安全代码位置，不格式化异常文本。
- SQLAlchemy Runtime 固定 `echo=False`、`hide_parameters=True`。SQL 可见性由
  `sqlalchemy.engine` Logger 和 `DATABASE_ECHO` 控制；Alembic 复用相同 Formatter。

当前可操作规则见 [Backend 日志](../modules/backend-logging/README.md)。

## 影响

- 新业务事件必须登记事件名、允许字段、字段类型和测试，不能依赖任意 `extra` 自动输出。
- Adapter 单次 I/O 可以保留 DEBUG 诊断，默认级别的业务影响由拥有业务结果的 Application 层记录。
- 日志平台、告警和查询必须使用 JSON 稳定字段；console 文案和 ANSI 颜色可以按人工阅读需要调整。
- 安全白名单会减少未知异常的诊断内容，需要结合 trace、异常类型和代码位置定位，不允许用回显
  请求数据或原始异常文本换取便利。
- 部署侧仍负责采集、传输、轮转、留存和访问权限；应用不自行写日志文件或连接远端日志平台。

## 调整条件

当部署平台要求标准化结构协议、分布式追踪需要跨服务传播，或当前安全异常摘要不足以在不泄漏数据
的前提下排障时，重新评估 Formatter、字段表和采集方式。调整时仍需保持单条业务记录只有一个输出
路径，并为敏感字段设置明确允许清单。
