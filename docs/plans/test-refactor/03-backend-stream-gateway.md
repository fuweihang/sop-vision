# 任务 3：Backend Stream Gateway 测试重构

> 本任务在独立 Codex 会话中执行。实施前先阅读[总计划与通用要求](./README.md)，完成并通过统一验证入口后再进入下一任务。

### 任务目标

重构 Stream Gateway 的 Port 数据规则、状态投影、URL、MediaMTX HTTP Adapter 和协议测试，明确区分
纯规则、静态协议兼容性、HTTP Client 边界与真实 MediaMTX 边界。

### 当前上下文与前置条件

现有测试位于 `backend/tests/modules/stream_gateway/`，共包含 ports、projection、urls、MediaMTX
adapter 和受控 OpenAPI 五组测试。任务 2 已经完成，Cameras 测试和命令均已使用标准目录；本任务
完成时移除最后一组 Backend 旧目录过渡规则和命令。

开始实施前必须满足：

- 提供有效的 `backend/.env.local` 或 `TEST_DATABASE_URL`。Stream Gateway integration 会影响
  Cameras，并使统一验证入口实际执行 Cameras integration。
- Docker daemon 可用，且本机已有 `bluenviron/mediamtx:1.20.1`，或当前环境允许 Docker 拉取该镜像。
- 真实 MediaMTX 门禁必须实际执行；不能把 Docker、镜像或数据库环境缺失造成的跳过当成通过。

### 实施范围

- `backend/tests/unit/stream_gateway/`：ports、projection 和 urls 的确定性规则。
- `backend/tests/contract/stream_gateway/`：仓库内受控 MediaMTX OpenAPI、固定版本和最小操作/字段集合。
- `backend/tests/integration/stream_gateway/`：基于 `httpx`、`respx` 的 Adapter 请求、分页、预算、错误、
  日志和敏感数据行为。
- 保留 `backend/scripts/check_mediamtx_contract.py` 和
  `backend/scripts/check_mediamtx_adapter.py`，并由 Stream Gateway integration 命令执行。
- `test-impact.json` 中 `backend-stream-gateway` 的源码、测试目录、三档命令和 Cameras 影响关系。
- `tests/unit/test_infrastructure/` 中对应的选择器与测试路径回归测试。

当前没有需要保留的 Stream Gateway module 测试，不创建
`backend/tests/module/stream_gateway/`。只有两个以上测试文件确实需要复用辅助代码时，才新增
`backend/tests/support/stream_gateway/`；单文件 Fixture 和 Builder 留在测试文件内。

### 明确不做

不修改生产行为，不移动或改写两个真实 MediaMTX 检查脚本，不为 FastAPI dependency 等框架胶水
补低价值测试，不处理 Backend Core、Cameras 或 Frontend Video 的测试内容，不搭建跨系统业务 E2E
环境。

现有两个脚本启动独立临时 MediaMTX 容器，分别验证真实协议和真实 Adapter，它们属于 integration
门禁，不属于本任务排除的 E2E。

### 实施步骤

1. 逐个确认现有测试要防止的缺陷，再按以下固定归属迁移，不按目录完整性增加测试：
   - `test_ports.py`、`test_projection.py`、`test_urls.py` 进入 `unit/stream_gateway`。
   - `test_mediamtx_openapi.py` 进入 `contract/stream_gateway`。
   - `test_mediamtx_adapter.py` 进入 `integration/stream_gateway`。虽然测试使用 `respx` 隔离真实服务，
     但它验证的是 `httpx` Client 请求和响应边界，因此属于 integration。
2. 重新检查测试价值，删除重复行为、只断言内部调用次数或无法说明实际缺陷的用例；不要为了创建
   module 层而测试 `get_stream_gateway` 等简单框架接线。
3. 删除 `backend/tests/modules/stream_gateway/` 中已迁移的测试并清理空目录；用 `rg` 确认没有 import、
   配置或命令继续引用该旧路径。
4. 更新 `test-impact.json`：
   - 移除 Stream Gateway legacy 测试路径和 `backend/tests/module/stream_gateway/**` 登记。
   - 保留 unit、contract、integration 三个实际测试目录，并分别登记为 unit、module、integration。
   - 把 `contracts/mediamtx-openapi.json` 加入 `backend-stream-gateway` 的 integration source 规则；
     保留它已有的 `frontend-video` 归属，因为共享协议输入可以影响多个模块。
   - 保留 `backend-stream-gateway` 对 `backend-cameras` 的影响关系。
   - 三档命令固定为：

     ```json
     "commands": {
       "unit": [
         "cd backend && uv run pytest tests/unit/stream_gateway"
       ],
       "module": [
         "cd backend && uv run pytest tests/unit/stream_gateway tests/contract/stream_gateway"
       ],
       "integration": [
         "cd backend && uv run pytest tests/unit/stream_gateway tests/contract/stream_gateway tests/integration/stream_gateway",
         "cd backend && uv run python scripts/check_mediamtx_contract.py",
         "cd backend && uv run python scripts/check_mediamtx_adapter.py"
       ]
     }
     ```

5. 更新 `tests/unit/test_infrastructure/test_test_changed.py`，至少确认：
   - unit、contract、integration 测试路径的登记级别分别是 unit、module、integration；由于
     Stream Gateway 会继续影响 Cameras，unit 和 contract 变化的最终全局执行级别均至少提升为
     module，integration 变化仍执行 integration。
   - `services/**`、两个检查脚本和 `contracts/mediamtx-openapi.json` 选择 integration。
   - Stream Gateway 源码变化继续影响 Cameras，并使用 Cameras 已迁移的新命令。
   - 三档命令按风险增加目录；integration 包含两个真实容器脚本；所有命令不再引用 legacy 路径。
6. 更新 `tests/unit/test_infrastructure/test_test_policy_check.py`：删除“迁移期间接受旧目录”的断言，
   确认 unit、contract、integration 新路径均被接受，并确认仍然存在的
   `backend/tests/modules/stream_gateway/` 测试会被拒绝。

### 验证方式

只运行：

```bash
./scripts/verify-changed.sh
```

确认 Test Infrastructure、Stream Gateway 及其影响的 Cameras 测试均通过；Cameras 数据库 integration
没有跳过，Stream Gateway integration 中两个真实 MediaMTX 容器门禁均实际执行并通过。失败时先用
`rg` 检索脚本给出的临时日志路径，只读取定位问题需要的片段。

### 完成标准与下一任务衔接

- Stream Gateway 测试只位于 unit、contract 和 integration 三个标准目录，legacy 与空 module 目录
  均不存在。
- 静态 OpenAPI、Mock HTTP Client 和真实 MediaMTX 容器分别保护明确且不重复的风险。
- `test-impact.json` 能按风险运行新目录和真实门禁，协议输入变化会选择 Stream Gateway
  integration，且 Stream Gateway 对 Cameras 的影响关系继续有效。
- 统一验证入口实际完成 Test Infrastructure、Stream Gateway 和 Cameras 验证。Backend Core 沿用
  任务 1 已通过的结果，本任务不额外声称重新验证 Core。

后续任务可以将 Core、Cameras 和 Stream Gateway 的既有结果作为 Backend 基准；下一任务只开始
Frontend Cameras 测试迁移。

## 导航

- [返回总计划](./README.md)
- [下一任务](./04-frontend-cameras.md)
