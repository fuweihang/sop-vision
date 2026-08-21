# 步骤 3｜领域模型与规范化规则

> 前置：Foundation 事实源；不依赖步骤 2 的 ORM 类型  
> 产出：框架无关的 Camera 聚合、值规则、固定 ID/时钟和领域 Fixture

## 1. 完成目标

用纯 Python 表达 Camera 聚合不变量，使 API、Repository 和测试共享同一套规范化逻辑。领域对象不能依赖数据库或 HTTP，也不能在 `repr` 中泄露凭据。

## 2. 领域产物

建议放置于 `app/modules/cameras/domain/`：

- `Camera` 聚合根和 `CameraSource` 实体。
- `CameraId/SourceId` 或等价 UUID v4 值类型。
- `CameraCredentials` 等不回显秘密的值对象。
- `normalize_name`、`normalize_url_suffix`、IPv4 和端口校验。
- RTSP URL 生成器；只在明确需要详情或 MediaMTX 上游配置时调用。
- `IdGenerator`、`Clock` 端口及生产/固定实现。
- 精确、可由 HTTP 层转换的领域校验错误。
- `CameraBuilder/CameraSourceBuilder` 测试 Fixture。

## 3. 聚合不变量

- Camera 和 Source ID 均为服务端生成 UUID v4，创建后不可改变。
- Camera 至少包含一路 Source，且恰好一路为默认源。
- 默认源 ID 必须属于当前 Source 集合。
- Source 后缀先 trim，再移除全部前导 `/`；结果为空则失败。
- 规范化后的同 Camera 后缀大小写敏感唯一。
- Source 数组顺序映射为从 `0` 开始的连续 `sort_order`。
- 重建持久化对象时若发现断裂排序、无 Source 或默认源不一致，应报告聚合损坏，不能静默修复。
- 已有 Source 更新保留 `source_id/created_at`；新 Source 使用生成器；聚合变更更新时间使用注入时钟。

不要新增名称/IP 唯一、在线校验、MediaMTX Path、播放状态或跨业务删除保护。

## 4. 敏感数据约束

- 密码字段和完整 RTSP URL 不参与默认 `repr/str`、异常 detail 或相等失败输出。
- 测试断言失败时不打印完整聚合秘密。
- RTSP URL 遵循 Foundation 已冻结的拼接语义；若未来需要修改特殊字符编码，必须先更新公共契约，不能在实现中静默改变。
- 领域事件、日志上下文和指标标签只允许 ID 与非敏感错误 code。

## 5. 实施顺序

1. 定义 ID、Clock、Secret 等最小值类型/端口。
2. 实现字符串、IPv4、端口和后缀规范化函数。
3. 实现聚合创建与持久化重建两条路径。
4. 实现 Source 集合替换/排序所需的领域操作，不接数据库。
5. 建立固定 ID/时钟和 Fixture Builder。
6. 补充敏感 `repr` 和错误文本回归测试。

## 6. 必测场景

- 固定生成器产生合法 UUID v4，并能稳定重放快照。
- trim 后空名称、非法 IPv4、越界端口失败。
- 多个前导 `/` 被移除，内部字符、大小写、查询字符串和尾 `/` 保持不变。
- `ABC` 与 `abc` 不重复，两个规范化后相同的后缀精确定位到后续重复项。
- 0 路 Source、0 个默认源、多个默认源和跨 Camera 默认源失败。
- Source 重排产生连续顺序但不改变已有 ID。
- `repr`、异常和测试日志不包含测试密码或完整 RTSP URL。

## 7. 退出条件

- 领域测试不启动 FastAPI、不连接 PostgreSQL、不访问 MediaMTX。
- 所有聚合不变量均有稳定错误 code 和字段路径信息。
- Fixture 可生成空数据库测试以外的单 Source、双 Source、十 Source 数据。
- 现有早期单流 Camera Schema 不再被任何新领域代码引用。

## 8. 后续交接

步骤 4 负责把这些对象映射到 ORM，不得复制规范化逻辑；步骤 6 负责把领域限制翻译为 Pydantic/OpenAPI，不得让 Pydantic 模型成为领域实体。
