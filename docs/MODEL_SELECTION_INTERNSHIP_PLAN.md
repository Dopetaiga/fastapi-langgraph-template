# 模型选择与可靠调用：实习项目实施方案

## 1. 目标

在不改变现有七类节点、不自研模型网关的前提下，为 Agent Runtime 增加：

- 用户指定某个具体聊天模型；
- 用户选择经济、均衡、高性能或自动策略；
- Runtime 在创建 Run 时校验并冻结模型选择；
- LiteLLM 继续负责供应商、部署、限流、短重试和故障转移；
- PostgreSQL Worker 负责 Run/Job 级恢复；
- 模型选择、路由、重试、耗时、Token 与成本均可观测。

这是一项面向实习展示的纵向功能，不扩展为动态 Provider 框架。

## 2. 架构边界

```text
Web UI
  -> FastAPI Model Catalog / Run API
  -> Runtime 校验并解析 ModelPolicy
  -> PostgreSQL 冻结本次 Run 的模型决策
  -> Worker / LangGraph 读取冻结结果
  -> ModelGateway 生成项目内 ModelRequest
  -> LiteLLM Proxy 选择实际 Provider Deployment
```

职责划分：

| 组件 | 负责 | 不负责 |
|---|---|---|
| 前端 | 展示模型、提交具体模型或策略 | 接触 LiteLLM Master Key、直接调用 LiteLLM |
| Runtime | 目录过滤、权限与能力校验、策略解析、冻结选择、任务级恢复 | Provider 密钥、部署负载均衡 |
| LangGraph | 使用 Run 已冻结的模型执行节点 | 维护模型目录、随意重选模型 |
| LiteLLM | Provider 调用、短重试、fallback、限流与成本数据 | Run 生命周期、checkpoint |
| PostgreSQL Worker | Job 租约、崩溃恢复、可恢复任务重试 | 单次 HTTP 调用内部重试 |

LiteLLM 和 Mem0 仍分别位于 `ModelGateway` 与 `MemoryStore` 的薄边界之后，
两者不互相依赖，任何一方不可用都不应迫使另一方更换实现。

## 3. 用户契约

前端提供两种模式：

```text
指定模型 -> 从允许目录中选择一个稳定 model_id
策略模式 -> auto | economy | balanced | performance
```

建议请求结构：

```json
{
  "model_policy": {
    "mode": "specific",
    "model_id": "gpt-4o-mini"
  }
}
```

```json
{
  "model_policy": {
    "mode": "tier",
    "tier": "balanced"
  }
}
```

Runtime 不接受未经目录校验的任意模型名。模型目录由 Runtime 通过服务端凭据读取
LiteLLM，并转换成面向产品的稳定响应。前端永远不读取 LiteLLM 密钥。

模型目录至少返回：

```text
catalog_id
display_name
capabilities: tools | structured_output | vision | streaming
selectable
availability: available | stale | unavailable
```

Embedding 模型不进入聊天模型选择列表。

## 4. 模型解析规则

创建 Run 时执行一次确定性解析：

1. 读取缓存的 LiteLLM 模型目录；
2. 校验模型可见性、节点需要的能力和允许范围；
3. `specific` 直接解析为允许的逻辑模型名；
4. `tier` 根据固定映射解析为 `agent-economy`、`agent-balanced` 或
   `agent-performance`；
5. `auto` 根据确定性规则选择一个档位，V1 不额外调用 LLM 做路由；
6. 将请求值、解析值、原因和目录版本写入 Run；
7. Worker 和 LangGraph 只读取冻结结果，保证恢复与重放一致。

节点级覆盖不是 V1 默认功能。只有图定义明确声明允许覆盖时才能使用，并且仍需经过
同一目录和能力校验。

## 5. 持久状态

建议为 Run 保存一个 JSONB 模型决策快照，避免第一版产生过多列：

```json
{
  "requested": {"mode": "specific", "model_id": "gpt-4o-mini"},
  "resolved_model": "gpt-4o-mini",
  "resolved_tier": null,
  "reason": "user_selected",
  "catalog_version": "...",
  "resolved_at": "..."
}
```

Run 状态保持现有生命周期：

```text
queued -> running -> paused -> completed
                  \-> failed | cancelled
```

模型调用重试不是新的 Run 状态，只产生事件和 Trace。

## 6. 重试与检查

### LiteLLM 调用级

- 负责 429、短时 5xx、连接抖动和同一逻辑模型组内 fallback；
- LiteLLM Proxy 最多进行 1 次短重试；Runtime 到 Proxy 的 SDK 调用不再重复重试；
- 参数、鉴权、能力不支持、上下文超限等确定性错误不重试。

### Runtime Worker 任务级

- 负责 Worker 崩溃、租约过期、数据库短暂故障和可恢复执行错误；
- 沿用 PostgreSQL Job 的 attempt、lease 和 next-attempt 机制；
- 建议最多 2 至 3 次，并使用 checkpoint 恢复；
- 不对确定性模型错误重新执行整个任务。

必须避免 Runtime 重试次数与 LiteLLM 重试次数无边界相乘。每次模型调用使用稳定的
`call_id`，外部副作用继续使用稳定的 `action_id`。

### 模型目录检查

- Runtime 缓存 LiteLLM 目录 30 至 60 秒；
- 刷新失败时可短期返回上一次成功快照，并标记 `stale`；
- 创建 Run 时进行严格校验；
- Worker 开始执行时只做轻量一致性检查，不主动逐模型探活；
- 实际调用失败由 LiteLLM 返回，Runtime 负责错误标准化。

模型能力不从模型名称猜测，也不默认所有模型都支持工具或结构化输出。V1 使用
`MODEL_CAPABILITIES` 显式静态配置；未配置模型返回空能力列表。

## 7. 信息流

前端提交的是产品语义：输入、图版本以及模型策略。LangGraph 状态接收的是已解析的
项目内模型决策，不包含 Provider Key 或 LiteLLM SDK 类型。ModelGateway 发送兼容
OpenAI 的请求：

```text
model
messages
temperature / max_tokens
tools / response_format（节点需要时）
stream
trace headers
metadata 中的低敏标识
```

LiteLLM 返回的文本、结构化结果、Token、成本、finish reason 和标准化错误进入
`ModelResult`；只有需要推进图执行的数据进入 AgentState。诊断数据进入事件、Trace、
Metric 和结构化日志，不把完整 Prompt、密钥或任意响应对象写入日志和指标标签。

## 8. 可观测性验收

新增或完善以下事件：

```text
model.catalog.refreshed
model.resolved
llm.requested
llm.retrying
llm.fallback
llm.completed
llm.failed
```

其中高频 Token 事件允许批量或仅经 SSE 临时传输，不要求逐 Token 写 PostgreSQL。

`llm.call` Span 至少包含低基数属性：请求逻辑模型、解析策略、节点类型、尝试序号、
结果类别、Token 与成本。Run ID、用户 ID 不作为 Metric Label。Grafana 应能回答：

- 用户请求了什么模型策略，最终解析成什么；
- 哪次调用发生重试或 fallback，原因是什么；
- 模型调用的成功率、P95、Token 和成本；
- 失败属于 LiteLLM 调用级还是 Worker 任务级。

## 9. 分阶段开发任务

### M1：目录与契约

- 增加项目内 `ModelPolicy`、目录响应和解析结果模型；
- 增加 Runtime 的 `GET /models`；
- LiteLLM 目录缓存与 stale fallback；
- 单元测试：过滤、缓存、非法模型、能力不匹配。

验收：前端可安全获取并显示具体模型列表。

### M2：Run 冻结与迁移

- Run API 接收 `specific/tier/auto`；
- 增加 Alembic 迁移并保存决策快照；
- Worker 读取冻结模型；
- 恢复和重放不因目录变化而换模型。

验收：数据库可以解释一次 Run 为什么使用该模型。

### M3：前端选择

- 添加“自动策略/指定模型”切换和能力提示；
- 目录 stale 或模型不可用时给出明确提示；
- Run 详情展示 requested、resolved 和 reason。

验收：用户既能选具体模型，也能选高中低/自动策略。

### M4：可靠调用与错误分类

- 配置 LiteLLM 短重试和逻辑模型组 fallback；
- ModelGateway 统一错误类别；
- Worker 仅重试可恢复任务错误；
- 增加 `call_id` 与重试预算测试。

验收：不会无限重试，也不会出现不可解释的重复调用。

### M5：事件、Trace 与面试演示

- 增加模型解析和调用事件；
- 完善 Span、Metric、日志与 Grafana 面板；
- 添加成功、fallback、无效模型、无密钥失败四条演示路径；
- 更新中英文 README 和本地启动手册。

验收：通过 UI、数据库和 Jaeger/Grafana 能完整解释一次请求。

## 10. 测试清单

- 目录成功、超时、空目录、stale 缓存；
- 指定模型成功、模型不存在、模型禁用、能力不匹配；
- 三档与 auto 的确定性映射；
- Run 创建后目录改变，冻结结果不变；
- LiteLLM 429/5xx 可短重试，401/400 不重试；
- Worker 崩溃后从 checkpoint 恢复；
- LiteLLM 重试与 Worker 重试总次数有上限；
- 事件顺序、Trace 关联、敏感字段脱敏；
- 前端不获得 LiteLLM Master Key；
- 真实 LiteLLM 测试配置的目录和一次成功模型调用。

## 11. 明天继续的顺序

```text
先做 M1 契约和测试
-> 再做 M2 数据库冻结
-> 再接 M3 前端
-> 最后做 M4/M5 重试与观测闭环
```

第一天不要同时实现 Token 级持久化、主动健康探测、智能成本优化或复杂动态负载均衡。
这些不是实习项目证明核心架构能力所必需的功能。

## 12. 完成标准

方案完成时必须满足：

- 七类节点和 Supervisor 控制流不变；
- LiteLLM 仍是唯一模型网关，Mem0 保持独立；
- 用户可指定具体模型，也可使用自动/三档策略；
- Run 的模型选择可恢复、可重放、可审计；
- 两层重试职责清晰且有总预算；
- 完整测试通过，并有一条真实端到端演示；
- README、架构文档和本地小白手册与实际命令一致。
