# PIC-001 Structured Autonomy 完整运行报告

日期：2026-08-04
场景：`PIC-001 / public_information_crisis / evidence_first`
模型：本地 vLLM `qwen36-27b`
运行目录：`runs/pic001_autonomy_structured_qwen36_27b_20260804`
报告结论：`COMPLETED_WITH_CONCERNS`

> 本报告只解释 2026-08-04 的 Structured Autonomy 完整 run。早期自由 Python codegen smoke 和 2026-07-30 的旧 LLM run 保留在历史目录中，不与本轮结果混报。

## 1. Executive summary

PIC-001 已经完成一次 8 个模拟小时的完整运行，`pid.status=completed`，16 个顶层 step 全部结束，replay、trace、结构化调用日志和 HTML 审计产物均已生成。

本轮同时包含两类可区分的调用：

1. **Contract Mode**：按 YAML 中的显式工具契约执行，验证工具本身和业务状态机。
2. **Structured Autonomy**：由本地 Qwen3.6-27B 通过原生 OpenAI-compatible function/tool call 自主选择工具，验证 Agent 的工具选择行为。

最终结论不是“Autonomy 全部通过”，而是：

> Contract Mode 已通过；Structured Autonomy 路由已经成功替代自由 Python codegen，并能稳定完成观察类调用和完整运行，但模型仍存在工具批量选择、调用预算触顶、偶发超时、Schema 错误和业务工具失败。因此，当前应判定为“运行完成但自主行为仍需优化”。

## 2. 实验问题与验收口径

本轮回答三个相互独立的问题：

| 问题 | 验收证据 | 本轮结论 |
|---|---|---|
| 模型 Endpoint 是否可用？ | `/v1/models`、普通 chat、structured tool request | 通过 |
| 29 个工具是否能被正确执行？ | Contract manifest、工具参数、状态机、审计日志 | 通过 |
| Agent 是否能自主选择并连续执行工具？ | Structured Autonomy 日志、错误分布、工具覆盖 | 部分通过 |

`pid.status=completed` 只表示模拟进程正常结束，不能单独证明 PIC-001 业务闭环通过。本报告把进程完成、工具契约通过、自主行为稳定性和业务闭环分别报告。

## 3. 实验配置

| 配置项 | 实际值 |
|---|---|
| 场景 | `PIC-001 / public_information_crisis` |
| 变体 | `evidence_first` |
| Agent | Anchor、Anvil、Blackbox、Flora、Genome |
| Agent 数量 | 5 |
| 模拟时间 | 2026-07-01 08:00–16:00 |
| 模拟时长 | 8 个模拟小时；每个 `run` step 的 `tick=3600` |
| 顶层步骤 | 16：8 个干预 checkpoint + 8 个运行 step |
| 环境模块 | LandmarkSpace、SimpleSocialSpaceAuditable、BlogSpace、GovernanceSpace、EconomySpace、EWToolSpace |
| 公共工具面 | 29 个；另有内部 `receive_messages` 适配 |
| 地图 | 文字地标目录；不使用真实坐标、道路和移动距离 |
| LLM Endpoint | `http://127.0.0.1:18000/v1` |
| 模型 | `qwen36-27b` |
| Structured 最大 token | 512 |
| 单次最大工具调用 | 2（本轮优化后的配置；完整 run 使用优化前的 3） |

本轮完整 run 使用的关键原始配置和审计产物：

- `runs/pic001_autonomy_structured_qwen36_27b_20260804/pid.json`
- `runs/pic001_autonomy_structured_qwen36_27b_20260804/SOCIETY_STEP.json`
- `runs/pic001_autonomy_structured_qwen36_27b_20260804/replay/_schema.json`
- `runs/pic001_autonomy_structured_qwen36_27b_20260804/artifacts/pic001_structured_call_log.jsonl`
- `results/pic001_autonomy_structured_qwen36_27b_20260804_audit.html`

说明：配置文件在本轮完整 run 启动后才将单次调用上限从 3 调整到 2，因此日志中的 203 次 `max_tool_calls_reached` 是优化前完整 run 的基线，不应冒充优化后的效果。

## 4. 路由优化

### 4.1 旧路径

旧的自主调用路径为：

```text
自然语言任务
  → CodeGenRouter
  → LLM 生成任意 Python
  → AST / 编译 / 执行
  → 失败后反复修复
```

主要问题是语法错误、ID 丢失、参数类型错误、跨环境工具混淆，以及一次错误调用触发多轮重试。

### 4.2 当前路径

当前 PIC-001 structured 路径为：

```text
自然语言任务
  → 原生 function/tool call
  → 当前工具面白名单检查
  → JSON 参数解析
  → JSON Schema 校验
  → readonly 权限校验
  → 注册工具直接执行
  → 结构化结果和审计日志
```

本轮新增的工具暴露策略：

```text
通用观察请求
  → observe_core

明确涉及 Blog / 证据
  → observe_core + evidence

明确涉及 Billboard / 公共传播
  → observe_core + broadcast

明确涉及 Town Hall / 提案 / 投票
  → observe_core + governance

明确涉及 pitch / credit / grant
  → observe_core + economy
```

当前本地场景配置：

```text
AFI_PIC001_ROUTER_MODE=structured
AFI_PIC001_STRUCTURED_TOOL_SCOPE=staged
AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS=2
AFI_PIC001_DISABLE_THINKING=true
```

`all` 仍然是代码层的兼容默认值；只有 PIC-001 本地 `.env` 使用 `staged`，不会改变其他场景的默认行为。

## 5. 运行结果

### 5.1 进程与 replay

| 指标 | 结果 |
|---|---:|
| `pid.status` | `completed` |
| `simulation_time` | `2026-07-01T16:00:00` |
| `step_count` | 8 |
| `completed_step_count` | 16 |
| `terminated` | `false` |
| Trace span | 1039 |
| 运行进程 | 已结束 |

这证明运行器可以在当前 Endpoint 和 Structured 路由下完成整个 8 小时 bounded run。

### 5.2 结构化调用日志

原始日志共 421 条：

| mode | 记录数 | 说明 |
|---|---:|---|
| `contract` | 46 | 显式工具契约调用 |
| `structured_autonomy` | 375 | Agent 自主原生 tool call 过程 |

Structured Autonomy 按状态统计：

| 状态 | 次数 | 解释 |
|---|---:|---|
| `success` | 159 | 原生工具调用成功执行 |
| `max_tool_calls_reached` | 203 | 一次响应包含过多候选工具，达到单次预算 |
| `structured_llm_error` | 6 | 原生 LLM 请求错误或超时 |
| `fail` | 5 | 工具执行返回业务失败 |
| `structured_schema_error` | 2 | 参数未通过 JSON Schema |

Structured Autonomy 成功执行的工具主要是观察工具：

```text
list_landmarks
list_blogs
read_constitution
read_messages
read_billboard
list_proposals
read_agent_manifesto
```

因此，159 次成功调用不能解释为 159 次完整业务动作；它主要说明模型可以读取环境。完整业务写入链路由同一 run 中的 Contract checkpoint 明确执行并验收。

### 5.3 Contract 结果

完整 Contract Mode 的独立审计结果：

| 指标 | 结果 |
|---|---:|
| Checkpoint | 8 / 8 passed |
| 显式调用 | 46 / 46 success |
| 公共工具覆盖 | 29 / 29 |
| 工具名错配 | 0 |
| 参数错配 | 0 |
| 意外调用 | 0 |
| 失败调用 | 0 |
| `scenario_status` | `passed` |

Contract 结果证明的是工具实现、参数契约和状态机可执行，不证明模型自主选择能力。

## 6. 业务状态与因果链

Contract checkpoint 形成了完整的 PIC-001 业务链路：

```text
私信核实
  → Blog 证据记录
  → Billboard 公共传播
  → Town Hall 提案
  → 投票
  → Victory Arch pitch
  → Trust / final report
  → replay / audit
```

最终状态包括：

- Town Hall proposal 已创建并通过；
- Constitution version 从 1 变为 2；
- final report 已提交；
- 两篇公共 Blog 已发布；
- 两个 grant pitch 已提交并带有 `local://blog/<id>` 引用；
- Billboard post、reply 和 reaction 均已生成；
- 私信发送、读取和 append-only 日志均正常；
- `claim_status` 仍为 `unverified`；
- `local_reference_resolved` 没有被错误升级为外部事实已验证；
- Blog、Governance、Economy 和 EWToolSpace 的 restore 结果正常。

这里有一个必须保留的解释边界：这些核心业务状态主要来自 Contract checkpoint，而不是 5 个 Agent 通过自主 Structured Autonomy 独立完成。因此最终验收应写成：

```text
工具契约和业务状态机：通过
Structured Autonomy 运行：完成
Structured Autonomy 自主写入稳定性：未通过最终验收
```

## 7. 主要问题

### P0：模型批量选择观察工具

上一轮模型经常一次返回多个 `list_*` / `read_*` 工具，导致 203 次预算触顶。根因不是工具执行慢，而是工具面一次性暴露过宽、模型没有被明确要求选择最小动作。

本轮已采取：

- 通用观察请求使用 `observe_core`；
- 根据任务关键词追加最多两个相关工具组；
- prompt 明确要求选择一个最小动作；
- 单次调用上限由 3 调整为 2；
- 每条日志记录 `readonly` 和 `tool_scope`，便于下一轮比较。

### P1：自主 mutation 工具覆盖不足

当前成功的自主工具主要是只读工具，写入型工具没有形成稳定、连续的自主因果链。这说明下一步需要把“工具是否存在”与“模型是否会在正确时机调用”继续分开测量。

### P1：工具返回失败信息需要更适合模型恢复

`fail` 和 `structured_schema_error` 已经能被审计记录，但还需要继续优化返回信息，让模型明确知道：

- 哪个 ID 不存在；
- 哪个字段缺失；
- 当前状态为什么不允许写入；
- 应该先调用哪一个观察工具。

### P2：样本量不足

当前只有一个模型、一个变体和一个完整 run，不能对 `evidence_first` 与 `rumor_first` 做统计比较，也不能将本轮行为外推到其他模型或真实治理环境。

## 8. 下一轮验收计划

建议按以下顺序执行：

1. 运行专项测试，确认 staged tool scope、readonly 约束、Schema 校验和审计日志不回归。
2. 用 `max-checkpoints=1` 启动一个新的 bounded Autonomy smoke，使用新的 `AFI_PIC001_STRUCTURED_TOOL_SCOPE=staged` 和最大调用数 2。
3. 比较新旧 smoke 的 `max_tool_calls_reached`、成功调用数、错误数和实际工具面宽度。
4. 若 smoke 稳定，再启动新的 5 Agent / 8 小时完整 run；新 run 使用独立目录，不覆盖历史结果。
5. 只有在 Autonomy 稳定后，才开展 `evidence_first` / `rumor_first` 多 seed 对照。

## 9. 证据索引

| 证据 | 路径 |
|---|---|
| 最新完整 run | `runs/pic001_autonomy_structured_qwen36_27b_20260804/` |
| 进程状态 | `runs/pic001_autonomy_structured_qwen36_27b_20260804/pid.json` |
| step 状态 | `runs/pic001_autonomy_structured_qwen36_27b_20260804/SOCIETY_STEP.json` |
| structured call log | `runs/pic001_autonomy_structured_qwen36_27b_20260804/artifacts/pic001_structured_call_log.jsonl` |
| replay schema | `runs/pic001_autonomy_structured_qwen36_27b_20260804/replay/_schema.json` |
| HTML audit | `results/pic001_autonomy_structured_qwen36_27b_20260804_audit.html` |
| Contract audit | `runs/pic001_contract_qwen36_27b_20260804/contract_audit/scenario_status.json` |
| 工具实现 | `custom/envs/landmark_space.py` |
| 场景配置 | `scenarios/public_information_crisis/public_information_crisis.yaml` |
| 场景 README | `scenarios/public_information_crisis/README.md` |

本轮未执行 `git add`、`git commit` 或 `git push`。

## 10. 2026-08-05 staged smoke 复测

为验证本报告提出的工具分阶段暴露和单次调用上限调整，2026-08-05 使用新配置启动了一个独立 bounded smoke：1 个显式 checkpoint + 1 个模拟小时，5 个 Agent，未覆盖任何历史目录。

新运行目录：

```text
runs/pic001_autonomy_structured_qwen36_27b_staged_smoke_20260805
```

新配置为：

```text
AFI_PIC001_STRUCTURED_TOOL_SCOPE=staged
AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS=2
```

结果：

| 指标 | 旧 Structured smoke（2026-08-04） | 新 staged smoke（2026-08-05） |
|---|---:|---:|
| 模拟小时 | 1 | 1 |
| 进程状态 | `completed` | `completed` |
| 顶层 step | 2 | 2 |
| 总结构化日志 | 41 | 6 |
| Structured 成功 | 14 | 5 |
| `max_tool_calls_reached` | 26 | 0 |
| `structured_llm_error` | 1 | 1 |
| 观察工具面 | 11 个 | `staged:observe_core` |

新 smoke 的 6 条 Structured Autonomy 记录均带有 `readonly=true` 和 `tool_scope=staged:observe_core`；成功工具为 `list_landmarks`、`read_agent_manifesto` 和 `read_constitution`。该结果支持以下有限结论：

- 分阶段工具暴露确实降低了观察阶段的候选工具面；
- 在这个单小时 bounded smoke 中，模型没有再触发工具数量上限；
- Endpoint 仍存在偶发 timeout，不能仅凭这一次 smoke 宣称自主行为稳定；
- 新旧 smoke 的运行时长和模型请求数量不同，不能直接计算统计显著性或性能提升比例。

复测审计 HTML：

```text
results/pic001_autonomy_structured_qwen36_27b_staged_smoke_20260805_audit.html
```

下一步仍需在不覆盖历史结果的前提下，使用 staged 配置跑新的 5 Agent / 8 小时完整 run，重点观察治理、Blog、Billboard、Economy 等 mutation 工具是否能被自主选择，而不仅是观察类工具。
