# Agent Runtime Starter — 面试介绍指南

> **[ Ox Alpha ]** 本文档由 Ox Alpha 基于全仓库代码审查与修复实践整理，
> 用于 Agent 开发岗位的面试讲解。配套问题清单见
> [`docs/CODE_REVIEW_FINDINGS.md`](CODE_REVIEW_FINDINGS.md)。

---

## 1. 一句话定位（30 秒版本）

> 我做了一个 **Agent Runtime 参考实现**：把 LangGraph Agent 从"能调用模型"
> 做成 **可持久化、可恢复、可观测、可测试的后端运行时**。技术栈是
> FastAPI + LangGraph + PostgreSQL/pgvector + LiteLLM + Mem0 + OpenTelemetry。

关键差异化表述：**这不是聊天机器人 Demo，也不是通用 Agent 平台**——它刻意收窄
用户可定制面（图拓扑、提示词、工具/RAG 范围、一级子代理），用工程约束换可靠性。

## 2. 架构主叙事（2 分钟版本）

```text
Client / WebUI → FastAPI API → PostgreSQL (runs/jobs/events/approvals/vectors)
                     │                │ FOR UPDATE SKIP LOCKED
                     └────────→ Durable Worker → LangGraph Runtime
                                                  Supervisor → Tool/RAG/Subagent/Approval
Model 调用 → ModelGateway(反腐层) → LiteLLM Proxy
长期记忆   → MemoryStore(反腐层)  → Mem0          （与 RAG、checkpoint 三者严格分离）
遥测       → OTel Collector → Jaeger/Prometheus/Loki/Grafana
```

讲解时强调三条主线：

1. **执行持久化**：Run/Job/事件/审批全部落 PostgreSQL；Worker 用
   `FOR UPDATE SKIP LOCKED` 认领任务，lease + heartbeat + 重试 + 过期回收。
2. **可控的图语义**：只有 7 种节点类型；Supervisor 是唯一控制流出口；
   能力节点执行后自动返回（不变式 A3），业务能力不允许膨胀成新节点类型。
3. **边界防腐**：LiteLLM/Mem0 藏在项目自有的 `ModelGateway`/`MemoryStore`
   后面，SDK 类型不进图状态、不进公共 API。

## 3. 必讲的技术深水区（面试官最可能追问）

### 3.1 Durable Queue 的并发正确性

- `SELECT ... FOR UPDATE SKIP LOCKED` 保证多 Worker 互斥认领；
- lease 所有权写入 `lease_owner`，心跳按 `lease_seconds/3` 续约；
- **租约丢失即取消 handler**：心跳续约失败会 cancel 正在执行的任务并放弃写状态，
  防止同一 Job 双执行产生重复外部副作用（at-least-once 语义下的关键防线）；
- 认领 SQL join runs 表过滤终态 Run，终态任务永不复活。

### 3.2 状态竞态：终态不可覆盖

- `_update_run` / `_set_run_status` 都是**条件 UPDATE**：
  `WHERE status NOT IN ('completed','failed','cancelled') OR status = 目标值`；
- 场景：用户在执行中取消 Run，Worker 稍后正常完成——没有条件更新就会把
  `cancelled` 覆盖成 `completed`，甚至重试分支会把已取消的 Run 改回 `queued`
  形成僵尸任务。这是我在审查中发现并用集成测试锁住的真实 bug。

### 3.3 LangGraph checkpoint 与 interrupt/resume

- 每次执行绑定 `thread_id = run_id`，checkpoint 存 LangGraph 原生表；
- 审批通过 `interrupt()` 暂停：图停在审批节点，Run 置 paused；
- 审批 API 决议后重新入队，Worker 用 `Command(resume=...)` 从断点继续；
- **幂等设计**：action_id = `run_id:node_id:SHA256(canonical_arguments)`，
  同参数重复触发不会创建第二条审批（approved action 至多消费一次）；
- 陷阱点（可作为亮点讲）：暂停的 thread 若被误投递全新输入，append reducer 会
  把用户消息翻倍——所以恢复前必须校验存在已决审批。

### 3.4 事件时间线的确定性

- 事件序号由数据库分配：`pg_advisory_xact_lock(hashtext(run_id))` +
  `max(seq)+1` + `(run_id, seq)` 唯一约束 → 多进程下单调且不重不漏；
- SSE 端点先重放后 tail，支持 `Last-Event-ID` 断线续传（容错解析）；
- 敏感字段落库前统一脱敏。

### 3.5 错误归一化与终止分类

- 所有模型错误经 `ModelGateway` 归一为 `NormalizedError(category, recoverable)`；
- 图执行层抛 `ModelCallError` 携带类别，运行时据此分类 termination_reason：
  - `supervisor_final`（模型控制的完成）
  - `max_steps`（recursion limit 强制终止）
  - `model_error[:recoverable|fatal]`
  - `cancelled`（运行时取消）
- 设计原则：**绝不混淆模型自主结束与运行时强制终止**。

### 3.6 子代理隔离（安全边界）

- 子代理只接收自包含 task package（task/selected_context/allowed_tools/schema），
  不共享 MainAgentState 引用；
- 工具白名单显式声明，未注册工具直接拒绝；
- 静态校验拒绝嵌套 subagent 图 + 运行时 depth guard 双保险；
- 主图只接收结构化 result patch。

### 3.7 Human-in-the-loop 的完整闭环

sensitive 工具不需要手动画审批节点：Tool 节点执行前检查所选工具的
`ToolRisk.sensitive` 元数据，自动走同一条 interrupt 审批门；拒绝则返回
`permission_denied` 的归一化 ToolResult 回到 Supervisor 继续决策。

## 4. 工程质量证据（展示仓库即可）

| 维度 | 事实 |
|---|---|
| 测试 | 184 个单元/契约测试 + 6 个真实 PG 集成测试（CI 强制执行） |
| 静态检查 | ruff 全绿；mypy 配置与现状一致（strict 化是登记在案的技术债） |
| CI | lint + alembic 迁移 + 单测 + pgvector 集成测试 |
| 可观测 | trace context 经 `jobs.trace_context` 跨进程恢复，一次请求一条分布式 Trace |
| 文档 | 架构不变式（A1–A11）、模块契约、测试 Oracle、审查记录齐全 |

## 5. 诚实的边界陈述（加分项）

主动说明"没做什么、为什么"，比吹功能更能体现判断力：

- Mem0 已接入 API 但**尚未挂进 Run 执行链路**（before-run retrieval /
  after-run extraction 是下一步）；
- 并行子代理委派未实现（SupervisorDecision 目前单目标）；
- replay 未实现；PDF 解析未做；
- 这些都登记在 `docs/CODE_REVIEW_FINDINGS.md` 第 D 节，有明确的优先级排序。

## 6. 高频追问预案

**Q: 为什么用 PostgreSQL 而不是 Redis/RabbitMQ？**
A: 当前规模下没有证明需要额外基础设施的需求；PG 一套系统同时承担
队列/checkpoint/事件/向量，运维面最小。架构文档 A10 明确了升级门槛。

**Q: 为什么自己写 DSL 而不用 LangGraph 的原生 API 直接建图？**
A: 用户定制面要小而安全：YAML 只暴露 7 种节点和边，语义校验（单 Supervisor、
禁嵌套子代理、不可达检测）在编译期拦截，业务能力无法突破运行时约束。

**Q: at-least-once 投递怎么保证副作用不重复？**
A: 两层——Job 层 lease 互斥 + 心跳丢租约即中止 handler；副作用层用稳定
action_id 幂等（审批至多消费一次）。完全 exactly-once 不承诺，靠幂等收敛。

**Q: 这次代码审查你最有价值的发现？**
A: 取消竞态三部曲：条件更新缺失导致 cancelled→completed 覆盖、错误重试分支
把已取消 Run 改回 queued 形成僵尸任务、以及心跳丢失后 handler 继续跑完造成的
双执行风险。三者都属于"低频但必然发生"的分布式正确性问题，全部用条件 UPDATE
+ 取消传播 + 租约失联即停修掉，并补了回归测试。

---

*Ox Alpha · Agent Runtime Starter · 分支 OxAplha*
