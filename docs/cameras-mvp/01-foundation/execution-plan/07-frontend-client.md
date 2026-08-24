# 步骤 7｜前端类型、Client 与错误映射

> 前置：[步骤 6](./06-openapi-contract.md)  
> 产出：OpenAPI 生成类型、类型化 Axios 边界、Problem 解析器和 Cameras Query Key

## 1. 完成目标

让 Frontend 不再手写 Cameras DTO，并把网络错误统一转换为页面和动态表单可以稳定消费的结构。本步骤不实现 Camera 页面业务请求。

## 2. 产物边界

建议结构：

```text
frontend/src/lib/api/
├── generated.ts        # 生成文件，不手工编辑
├── client.ts           # Axios 实例与类型化请求边界
├── problem.ts          # Problem 解析和字段错误映射
└── camera-query-keys.ts
```

- 增加固定版本的 OpenAPI TypeScript 生成器和 `api:generate` 脚本。
- 生成类型只能来自 `contracts/openapi.json`。
- 现有 `api-client.ts` 迁移到单一 Client 入口，不能保留两个配置不同的 Axios 实例。
- 非 Problem 网络错误转换为明确的 transport error；不得伪造业务 code。
- 响应日志、错误上报和开发工具不得自动序列化含密码的 CameraDetail。

## 3. Problem 解析

- 先验证 `status/code/errors/context` 的运行时形状，不能仅依赖 TypeScript 静态类型。
- 未知或非 JSON 响应保留 HTTP 状态和安全通用消息，不显示原始 HTML/响应体。
- `errors[].field` 映射到 React Hook Form 可接受的动态路径。
- `sources[1].name`、`sources[1].url_suffix`、`sources[1].source_id` 均保持准确索引。
- 同字段多个错误保留确定顺序；全局错误不能错误挂载到某个输入框。
- UI 业务分支只用稳定 code，不比较中文 `title/detail`。

## 4. Query Key 工厂

公共 API 只暴露 Foundation 冻结的三个函数：

```text
cameras({q, page, page_size}) → ["cameras", {q, page, page_size}]
camera(cameraId)  → ["camera", cameraId]
playback(sourceId) → ["playback", sourceId]
```

- `filters` 只包含 `q/page/page_size`；进入 key 前规范化空 q，并让默认分页有唯一表示。
- 列表没有排序 filter；旧 `sort` 不得进入 OpenAPI 生成类型或 Query Key。
- 对象键顺序不能制造不同缓存项。
- Query 数据只使用内存缓存，不配置 localStorage/IndexedDB 持久化。
- 含密码的 CameraDetail 不进入持久化 Query cache、错误上报或离线缓存。

## 5. 实施顺序

1. 添加生成器、脚本和 generated file header。
2. 从现有 Axios 配置迁移单一 Client，并保持 `VITE_API_BASE_URL` 行为。
3. 实现 Problem 运行时解析和安全 transport error。
4. 实现嵌套字段映射。
5. 实现 Query Key 工厂和 filters 规范化。
6. 用生成类型编写编译期契约测试，删除重复手写 DTO。

## 6. 必测场景

- OpenAPI 重新生成后 TypeScript build 无手工补丁。
- 标准 Problem、字段 Problem、非 JSON 502、网络中断均被安全分类。
- 嵌套 Source 错误映射到准确数组行。
- 空 q、空白 q 和未提供 q 生成相同 key。
- Camera/Source ID 在 key 中保持 canonical 字符串。
- 错误对象、console spy 和持久化存储中不出现测试密码或完整 RTSP URL。

## 7. 退出条件

- Cameras HTTP DTO 没有第二份手写 TypeScript 定义。
- 生成文件可被脚本完整覆盖，lint/format 不要求人工修改生成代码。
- Client、Problem parser 和 Query Key 可在没有 Camera 业务页面时独立测试。
- Frontend build、lint 和定向测试通过。

## 8. 后续交接

步骤 8 使用同一生成类型构建 MSW Fixture。业务页面只消费 Client 返回的 typed result/problem，不直接解析 AxiosError。
