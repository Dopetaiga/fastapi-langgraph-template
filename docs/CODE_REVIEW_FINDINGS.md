# 代码检查发现与修复记录（OxAplha 分支）

> 检查范围：全仓库代码审查，重点是可用性、鲁棒性、路线图完成度。
> 基线验证：`pytest` 168 passed / 3 skipped；`ruff` 全绿；`mypy --strict` 134 错误（未纳入 CI）。
> 本文档是本分支修复工作的依据，每项标注状态：✅ 已修复 / 🔜 已缓解 / ⏸ 暂缓。

---

## A. 鲁棒性问题

### A1. 取消竞态：cancelled 状态会被覆盖 【高】 — ✅ 已修复

- 现象：`cancel_run` 设置 `cancelled` 后：
  - 正在执行的 Run 完成时被 `RunManager._update_run` 无条件覆盖为 `completed/failed`；
  - 执行中抛错且重试未耗尽时，`WorkerQueue._set_run_status` 把已取消的 Run 改回
    `queued`，留下永远不会被认领的僵尸任务；
  - worker 收到 handler 返回的终态（如 cancelled）仍会写 `completed`。
- 违反契约：`docs/modules/PERSISTENCE_WORKER.md` "honor cancellation"。
- 修复：
  - `_update_run` / `_set_run_status` 改为条件 UPDATE（终态不可覆盖，允许同值写入）；
  - worker 对 handler 返回的 paused/cancelled/failed 终态不再写 completed；
  - 图执行节点在执行前通过注入的 `cancel_check` 检查 Run 状态，已取消则抛
    `RunCancelledError`，`execute_run_sync` 归类为 cancelled 终态。

### A2. Worker 主循环无兜底 【高】 — ✅ 已修复

- 现象：`run_forever` 中 `claim_next` 等数据库瞬时异常会直接击穿循环，worker 进程崩溃退出。
- 修复：`run_once` 异常在 `run_forever` 内捕获并按指数退避重试（上限封顶），
  正常处理任务后重置退避。

### A3. 模型错误绕过归一化体系 【高】 — ✅ 已修复

- 现象：`_run_llm` / `_run_supervisor` 失败时抛裸 `RuntimeError`，
  绕过项目自有的 `NormalizedError/ErrorCategory`，违反 DoD 的错误归一化要求。
- 修复：新增 `ModelCallError(AppError)` 携带 `ErrorCategory` 与 `recoverable`；
  图节点统一抛出该类型；`execute_run_sync` 将其归类为独立 termination_reason
  `model_error`。

### A4. 重复 run.started 事件 【中】 — ✅ 已修复

- 现象：每次重试、审批恢复都会再发一次 `run.started`，破坏事件时间线语义。
- 修复：`RuntimeEventRepository.has_event()` 幂等判定，仅首次执行发射 `run.started`。

### A5. 暂停 Run 的误恢复路径脆弱 【中】 — ✅ 已修复

- 现象：paused Run 在审批未决时若被再次投递，会对已有 checkpoint 的 thread
  重新 `ainvoke` 全新输入（messages reducer 为 append），导致用户消息翻倍。
- 修复：`execute_run_sync` 检测到 `status == paused` 且无已决审批时直接返回当前
  状态，不触碰 checkpoint thread。

### A6. SSE Last-Event-ID 解析崩溃 【中】 — ✅ 已修复

- 现象：非数字 `Last-Event-ID` 头导致 `int()` 抛 `ValueError` → 500。
- 修复：解析失败回退到 `after_seq` 参数（符合 SSE 重连语义的宽容处理）。

### A7. pyyaml 未声明为直接依赖 【中】 — ✅ 已修复

- 现象：`app/graph/loader.py` 直接 `import yaml`，但依赖来自 litellm 传递引入，
  上游变更即断。
- 修复：`pyproject.toml` 显式添加 `pyyaml>=6.0` 并刷新 lock。

### A8. 心跳丢失后不终止 handler 【中】 — ✅ 已修复

- 现象：lease 过期被其他 worker 抢走后，原 worker 的 heartbeat 返回 False 只是
  静默退出心跳循环，handler 继续跑完 → 同一 Job 双执行（违反 at-least-once 语义下
  的副作用约束）。
- 修复：heartbeat 失败即取消 handler 任务，`run_once` 将其归类为 lease 丢失，
  不写 fail/终态（所有权已转移）。

### A9. checkpointer 每个 Job 重建连接池并执行 setup DDL 【低】 — ✅ 已修复

- 修复：`postgres_checkpointer` 按连接串记忆 setup 完成状态（进程级幂等），
  DDL 只在首个 Job 执行。

### A10. 杂项清理 【低】 — ✅ 已修复

- `routing.py` 死分支删除；
- `get_session` 注解改为 `AsyncIterator[AsyncSession]`；
- `_run_subagent` 用 `dataclasses.asdict` 替代 `result.__dict__`；
- `validator.py` 补充入口存在性与不可达节点校验（含 supervisor 能力隐式边）。

## B. 可用性问题

### B1. POST /runs 不做运行时预检 【中】 — ✅ 已修复

- 现象：`entry` 不指向真实节点等问题到 Worker 执行时才失败，用户看到创建成功但
  Run 直接 failed。
- 修复：`create_run` 时以 LangGraph 编译规则做 dry-run 校验，非法图返回 422。

### B2. mypy strict 配置形同虚设 【中】 — 🔜 已缓解

- 现象：pyproject 声明 `strict = true`，实际 134 个错误且 CI 不跑 mypy，配置误导。
- 处理：降级为务实配置（移除 strict），完整 strict 化列入技术债（见 D 节）。

### B3. 敏感工具不会自动触发审批 【中】 — ✅ 已修复

- 现象：`ToolRisk.sensitive` 元数据无任何消费方，审批只能作为显式图节点使用。
- 修复：Tool 节点执行前检查所选工具 risk；sensitive 工具复用审批 interrupt 流程
  （稳定 action_id、持久化 PendingAction、reject 时返回 permission_denied 结果），
  关闭 Phase 8 "sensitive tool integration" 缺口。

### B4. max_steps 终止与模型终止混淆 【中】 — ✅ 已修复

- 现象：recursion limit 触发时 `termination_reason="error"`，违反“不得混淆模型控制
  的完成与运行时强制终止”。
- 修复：捕获 `GraphRecursionError`，`termination_reason="max_steps"`，
  提取纯函数 `_classify_failure` 便于确定性测试。

## C. 测试与 CI

### C1. CI 未运行 PostgreSQL 集成测试 【高价值】 — ✅ 已修复

- ci.yml 增加 `alembic upgrade head` 与 `RUN_POSTGRES_INTEGRATION=1`，
  checkpoint/审批恢复/pgvector 三条集成链路进入 CI 门禁。

### C2. 新增回归测试 — ✅ 已修复

- 取消终态不被覆盖（worker 层）；
- 心跳丢租约取消 handler；
- `run_forever` 瞬时故障存活；
- 模型错误归一化类别；
- sensitive 工具触发审批 interrupt 与拒绝路径；
- max_steps 终止分类（`_classify_failure`）;
- validator 入口/不可达节点；
- SSE 非法 Last-Event-ID 回退；
- 集成层：stale lease 回收、双 worker 争抢互斥、取消后完成不复活。

### C3. TEST_ORACLES 中仍未覆盖的分区 ⏸ 暂缓

- replay 不改历史、图 YAML 变更后恢复绑定快照版本（实现本身存在，缺专项测试）、
  duplicate delivery 外部副作用（action_id 幂等已有集成路径，缺显式用例）。

## D. 路线图缺口（暂缓，需独立设计，不在本 bugfix 分支实施）

| 缺口 | 路线图出处 | 说明 |
|---|---|---|
| Mem0 接入运行链路 | Phase 9 | before-run retrieval 与 after-run extraction 完全缺失，MemoryStore 仅暴露手动 API；需要定义记忆读写挂点与失败降级策略 |
| 并行子代理委派 | Phase 6 | 验收要求并行 delegation；`SupervisorDecision` 目前单目标，需扩展多任务 fan-out 与 `max_subagent_parallelism`（现为死代码 RuntimeGuard） |
| Replay | Phase 7 | 从 checkpoint 重放历史不改原始 Run，需产品语义确认 |
| PDF 解析 | Phase 5 | ingest 仅支持文本 |
| mypy strict 达标 | Phase 12 | 134 错误清零后恢复 strict 门禁 |
| `step_count` 列从未写入 | Phase 3/7 | 需要决定口径（节点数 vs LLM 调用数）后再接线 |

---

## 修复验证

```powershell
uv run ruff check app tests alembic
uv run pytest -q
$env:RUN_POSTGRES_INTEGRATION = "1"; $env:DATABASE_URL = "..."; uv run pytest tests/test_postgres_integration.py
```
