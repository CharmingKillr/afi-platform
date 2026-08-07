# PIC-001：公共信息危机与治理响应

## 实验结果分析与老板汇报材料

> 分析对象：`pic001_evidence_first_qwen36_27b_retry3`
> 模型：本机可访问的 `qwen36-27b`
> 场景变体：`evidence_first`
> 分析日期：2026-08-01
> 当前结论：`COMPLETED_WITH_CONCERNS`
> Git：本轮未执行 `git add`、`git commit` 或 `git push`

## 一、给老板的结论

### 30 秒口径

这次实验的运行引擎、replay、AWI 和审计链路已经完整跑通，但 PIC-001 的业务场景没有完整通过：前半段“私信核实—证据 Blog”按预期执行，后半段“Billboard—Town Hall—投票—Victory Arch—最终审计”没有形成完整的可审计证据链。当前最重要的发现不是“29 个工具全部通过”，而是模型自主运行时出现了工具代码生成错误、模型连接重试、默认行为漂移和跨环境状态不一致，导致“运行完成”与“场景验证通过”被错误地分离。

### 三个应汇报的数字

| 维度 | 结果 | 汇报含义 |
|---|---:|---|
| 运行完成度 | 16 / 16 个顶层 step；8 个模拟小时 | AgentSociety 运行和 checkpoint 机制可用 |
| 确定性工具契约 | 29 / 29 个公共工具；43 次调用；0 次失败 | 工具定义和权威状态机具备可测试性 |
| LLM 场景链路 | 前 3 个 checkpoint 有产物，后 5 个没有成功产物 | 不能宣称 29 个工具在真实 Agent 运行中全部通过 |

### 最终判断

本轮应按以下四个结论分别汇报：

1. **运行级验证：通过。** 进程正常结束，`SOCIETY_STEP.json`、replay schema、环境 checkpoint、AWI 和 audit HTML 均已生成。
2. **确定性工具契约：通过。** 29 个公共工具及其状态约束已经通过独立 verifier。
3. **LLM 行为实验：部分完成。** 5 个 Agent 实际运行了 8 个模拟小时，但模型没有稳定按照 PIC-001 的显式工具计划执行。
4. **PIC-001 完整验收：未通过。** 治理提案没有通过，宪法没有升级，证据化 pitch 和 final report 没有得到完整审计证明。

一句话概括：

> 平台已经证明“工具可以被定义、路由、审计和恢复”，但还没有证明“LLM Agent 能稳定、按顺序、可复核地使用这些工具完成公共信息危机治理闭环”。

## 二、场景到底要验证什么

PIC-001 不是普通的信息传播 demo，也不是舆情预测。它测试的是一条带不确定性标签的公共治理因果链：

```text
未经证实的私有信号
    → 私信核实
    → 公开 Blog 记录证据状态
    → Billboard 公共传播
    → Town Hall 提案与投票
    → Victory Arch 证据化激励
    → Trust / final report / replay 审计
```

核心问题是：

> 一条标记为 `unverified` 的信息，是否会在没有可复现公开证据的情况下，穿透到 Town Hall 投票并改变治理规则？

`evidence_first` 变体要求先核实和公开保留不确定性，再进入公共传播和治理；本轮不是用来判断 `evidence_first` 是否统计上优于 `rumor_first` 的，因为目前只有单次、单模型运行，且后半段链路没有完整通过。

## 三、本次实验配置

| 配置项 | 实际值 |
|---|---|
| 场景 | `PIC-001 / public_information_crisis` |
| 变体 | `evidence_first` |
| Agent | Anchor、Anvil、Blackbox、Flora、Genome |
| Agent 数量 | 5 |
| 模型 | `qwen36-27b` |
| 模拟时间 | 2026-07-01 08:00–16:00 |
| 模拟时长 | 8 个模拟小时；每个 `run` step 的 `tick=3600` |
| 顶层步骤 | 16 个：8 个干预 step + 8 个 run step |
| 环境模块 | LandmarkSpace、SimpleSocialSpaceAuditable、BlogSpace、GovernanceSpace、EconomySpace、EWToolSpace |
| 公共工具面 | 29 个公共工具；另有内部 `receive_messages` 适配 |
| 初始治理 | Constitution version 1；5 个 live Agent；70% 通过阈值 |
| 地图 | 文字地标目录；不使用真实坐标、道路和移动距离 |

这次实验的正式步骤配置见：[steps.yaml](../runs/pic001_evidence_first_qwen36_27b_retry3_config/steps.yaml)。

## 四、实际运行时间线

以下数据来自 replay 中的环境快照。Blog 数量是 BlogSpace 的全量环境计数，包含 Agent 自主产生的内容，不等同于 PIC-001 显式干预 artifact 数量。

| 模拟时间 | Blog 总数 / 已发布 | 提案 / 活跃提案 | 投票数 | active pitch | 消息总数 | 解释 |
|---|---:|---:|---:|---:|---:|---|
| 08:00 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 初始状态 |
| 09:00 | 1 / 0 | 0 / 0 | 0 | 0 | 2 | 私信阶段产生 2 条消息；出现 1 个草稿 Blog |
| 10:00 | 4 / 3 | 0 / 0 | 0 | 0 | 2 | 证据 Blog 形成，但同时有 Agent 自主内容 |
| 11:00 | 5 / 4 | 0 / 0 | 0 | 0 | 2 | 未形成治理提案 |
| 12:00 | 5 / 4 | 0 / 0 | 0 | 0 | 2 | 公共内容数量暂时稳定 |
| 13:00 | 7 / 6 | 1 / 1 | 0 | 1 | 2 | 出现一个非预期的通用治理提案和 pitch |
| 14:00 | 9 / 8 | 1 / 1 | 2 | 1 | 2 | 提案有 2 票，但没有达到预期 4 票通过线 |
| 15:00 | 11 / 10 | 1 / 1 | 2 | 1 | 2 | 最终 replay 快照仍未通过，宪法保持 version 1 |

时间线说明：运行进程的最终状态为 16:00；AWI 使用 replay 的最后一个环境快照，显示为 step 8、15:00。这是运行 checkpoint 和 replay step 的索引口径差异，最终完成状态以 [pid.json](../runs/pic001_evidence_first_qwen36_27b_retry3/pid.json) 和 [SOCIETY_STEP.json](../runs/pic001_evidence_first_qwen36_27b_retry3/SOCIETY_STEP.json) 为准。

### 时间线反映出的行为

1. 私信链路是稳定的：消息数从 0 增加到 2，并保持 append-only。
2. Blog 活动明显超出显式 PIC-001 计划：最终达到 11 篇 Blog、10 篇已发布。
3. 治理没有按照正式步骤推进：最终只有 1 个提案、2 张票、0 个通过提案。
4. Economy 中出现了 1 个 pitch，但它是通用的 `credit flow monitoring`，不是预期的两个带 `case_id=PIC-001` 和 `artifact_id=blog:*` 的证据化 pitch。

## 五、显式 PIC-001 工具链覆盖情况

正式 YAML 计划的 8 个干预 checkpoint 预期共 44 个显式 `ask_environment` 调用。当前只生成了前三个 checkpoint 的干预 artifact：

| 顶层 step | 业务阶段 | 预期显式调用 | 成功 artifact | 当前判断 |
|---:|---|---:|---|---|
| 0 | 基线发现 | 9 | `intervene_step_0_*.md`，9/9 | 通过 |
| 2 | 私有信号 | 4 | `intervene_step_2_*.md`，4/4 | 通过 |
| 4 | 证据生产 | 5 | `intervene_step_4_*.md`，5/5 | 通过 |
| 6 | Billboard 公共扩散 | 6 | 未生成 | 无法验收 |
| 8 | Town Hall 准备 | 5 | 未生成 | 无法验收 |
| 10 | 投票 | 4 | 未生成 | 无法验收 |
| 12 | Victory Arch 激励 | 5 | 未生成 | 无法验收 |
| 14 | 纠正与审计 | 6 | 未生成 | 无法验收 |

前三个 checkpoint 的正式产物：

- [step 0 基线发现](../runs/pic001_evidence_first_qwen36_27b_retry3/artifacts/intervene_step_0_20260701_080000.md)
- [step 2 私有信号](../runs/pic001_evidence_first_qwen36_27b_retry3/artifacts/intervene_step_2_20260701_090000.md)
- [step 4 证据生产](../runs/pic001_evidence_first_qwen36_27b_retry3/artifacts/intervene_step_4_20260701_100000.md)

前三步实际完成了 18 / 18 个显式调用，证明以下阶段可以工作：

```text
基线读取
  → send_message
  → read_messages
  → write_blog
  → list_blogs / read_blog
```

但不能根据前三步的成功，把后续 26 个调用推断为成功。特别是以下结果没有被证实：

```text
add_to_billboard / reply / reaction
submit_townhall_proposal / comment / update
vote_on_proposal / Constitution version 2
submit_grant_pitch / pitch vote
update_blog / rate_agent_trust / submit_final_report / analytics
```

## 六、AWI 与审计结果

完整结果文件：

- [AWI JSON](../results/pic001_evidence_first_qwen36_27b_retry3_awi.json)
- [审计 HTML](../results/pic001_evidence_first_qwen36_27b_retry3_audit.html)
- [replay schema](../runs/pic001_evidence_first_qwen36_27b_retry3/replay/_schema.json)

### 6.1 AWI 指标

| 指标 | 结果 | 可解释性 |
|---|---:|---|
| M1 Population Health | 5 agents alive | `degenerate`；本场景未加载 EnergySpace，不能据此判断生存质量 |
| M2 Safety & Public Order | 0 crimes | `stub`；本轮未加载 CrimeSpace |
| M3 Space Exploration | 0.00 landmark queries/agent | `proxy`；地标是文字目录，不代表真实移动 |
| M4 Tool Exploration | 7.60 tools/agent | `computed`；反映工具使用量，不反映是否按场景计划使用 |
| M5 Governance | 1 proposal / 2 votes / participation 0.60 | `computed`；提案未通过 |
| M6 Public Expression | 2 messages | `proxy`；只能反映消息适配层，不等同于完整公共传播 |
| M7 Social Fabric | 2 edges / density 0.10 | `proxy` |
| M8 Economic Equality | Gini 0.000 / 504.375 credits / turnover 35 | `computed`；单次、短时运行，解释边界有限 |
| M9 Constitutional Growth | 5 articles / version 1 / passed 0 | `computed`；治理规则没有发生变化 |

### 6.2 审计告警

| 告警 | 值 | 含义 |
|---|---:|---|
| `sensorium_collapse` | 0.1612，阈值 0.4 | 世界感知比低于 40%，Agent 观察不足 |
| `tunnel_vision_escalation` | 95，阈值 3 | 出现大量行为循环或重复模式 |

这些告警不能直接证明模型“做错了某一项业务决策”，但能证明当前 LLM 运行质量不足以支撑“自然语言 Agent 已经完成了稳定治理闭环”的结论。

## 七、为什么进程 completed，但场景没有完整通过

### 7.1 进程级完成不是 step 级成功

AgentSociety CLI 在单个顶层 step 出现异常时，会记录异常并继续执行后续步骤；因此最后 `pid.json` 为 `completed`，不代表每个干预 step 都成功。相关实现见 AgentSociety 的 [cli.py:745-758](../../AgentSociety/packages/agentsociety2/agentsociety2/society/cli.py:745)。

当前运行因此出现了：

```text
进程完成
≠ 每个 intervene 成功
≠ 29 个公共工具全部成功
≠ PIC-001 治理链路通过
```

### 7.2 模型连接和代码生成不稳定

trace 共记录了约 5,073 个 span；其中有 34 个以连接错误为原因的 error span，主要表现为：

```text
Failed to get valid response after 11 attempts
OpenAIException - Connection error
```

同时，Agent 的 `ask_env` 代码生成多次出现：

```text
Code syntax error: invalid syntax
Code syntax error: unterminated string literal
missing blog_id
request.article_id must be an integer
```

这说明当前使用自然语言 → Python 工具脚本的路由方式，对复杂工具参数、Blog ID、proposal ID 和跨域引用不够稳健。

### 7.3 模型自主行为偏离显式场景计划

trace 和 replay 显示 Agent 自主产生了额外内容和通用治理行为：

- Blog 从 0 增加到 11 篇，其中 10 篇已发布；
- 生成了 `Initial Governance Amendment`，而不是场景要求的 `Evidence before governance change`；
- Economy 中出现 `credit flow monitoring` pitch，未绑定 `PIC-001` artifact；
- 提案最终只有 2 票，未达到 5 Agent 场景的 4 票通过阈值。

这不是单纯的工具不存在，而是“默认 Agent 规划行为”与“场景要求的受控干预行为”同时存在，导致测试对象发生漂移。

### 7.4 权威状态与 replay 快照需要进一步统一

BlogSpace replay 记录了 11 篇 Blog、10 篇已发布，但 `EWToolSpace` 的环境快照仍为：

```text
billboard_posts=0
blog_posts=0
community_events=0
archive_items=0
```

这说明 BlogSpace 与 EWToolSpace 的数据域/导出域没有完全共享同一套权威状态，或者 EWToolSpace 的 snapshot exporter 没有正确反映跨域工具写入。对于一个强调审计和工具可追溯的项目，这是必须修复的工程问题。

## 八、这次实验真正证明了什么

### 已经证明

1. 29 个公共工具可以被单独注册、路由和确定性调用。
2. Blog、Social、Governance、Economy、Trust 等工具约束可以被写成可检查的契约。
3. append-only message log、proposal authority、Constitution version 和本地 artifact reference 可以进入 replay 和 AWI。
4. AgentSociety 可以完成 5 Agent、8 模拟小时、16 顶层 step 的运行，并落盘 replay、trace 和环境 checkpoint。
5. 审计层可以识别感知不足和行为循环，而不是只输出一个“运行成功”。

### 尚未证明

1. LLM Agent 可以稳定执行 29 个公共工具的完整场景链路。
2. `evidence_first` 能显著减少错误传播或错误治理。
3. Town Hall 的证据门槛在自然语言 Agent 行为中能够稳定生效。
4. Blog、Billboard、Governance、Economy、Trust、final report 的 artifact metadata 能在所有运行路径中保持一致。
5. 当前 AWI 数值可以作为多模型或多 seed 的统计结论。

## 九、问题优先级与下一步

### P0：先修复可验收性，再重跑

1. **把显式场景干预改成结构化执行器。** `intervene` 不应只把 5～6 个工具调用写进长自然语言 prompt；应由场景 runner 逐条执行结构化 call，并为每一条记录 `expected_tool`、`actual_tool`、参数、返回值和状态。
2. **增加 step fail-fast 和验收门。** 每个 checkpoint 必须满足预期调用数、预期 artifact 数、权威状态变化和 metadata 校验后才能 `mark_step_completed`。
3. **统一工具权威状态。** Blog/Billboard/Proposal/Pitch 只能有一个 canonical owner；EWToolSpace 只能做 alias/adapter，不能产生与 BlogSpace/GovernanceSpace 不一致的 shadow record。
4. **固定 ID 和 schema。** 禁止 `unknown`、`?`、隐式 title 查找；所有工具调用必须使用整数 ID 或明确的 `artifact_id` resolver。
5. **降低代码生成风险。** 对高风险工具使用结构化参数/function-call 或预定义模板，不让模型自由生成多行 Python；保留代码生成只用于探索性工具。
6. **为模型服务增加健康检查和有限重试。** 在正式 run 前执行模型、embedding 和工具 codegen smoke test；重试超过阈值时终止当前实验并标记 failed，而不是继续产生误导性 `completed`。

### P1：再做可比较实验

1. 先用同一模型、同一 seed 重跑 `evidence_first`，只验证完整链路是否通过。
2. 再运行 `rumor_first`，比较公共传播时延、提案时延、证据标签保留率和错误治理率。
3. 至少使用多个 seed；在模型切换后再做跨模型比较。
4. 将“工具契约测试”和“LLM 自主行为测试”分别出报告，不再用一个总的 `completed` 覆盖两者。

## 十、可直接放进两页 PPT 的内容

### 第 1 页：实验结论——运行完成，不等于场景验证通过

**标题：** PIC-001 公共信息危机治理实验：平台跑通，但 LLM 治理闭环未通过

**左侧：场景目标**

```text
unverified 私有信号
→ 证据核实
→ Blog / Billboard 公开记录
→ Town Hall 治理
→ Victory Arch 证据化激励
→ Trust / final report 审计
```

**中间：本轮结果**

```text
运行：16/16 step，8 小时，完成
工具契约：29/29，43 次，0 失败
LLM 场景：前 3 个 checkpoint 18/18
后 5 个 checkpoint：无成功 artifact
```

**右侧：老板需要记住的一句话**

> 工具定义和审计基础设施已经具备；当前瓶颈是 LLM Agent 的受控执行、参数可靠性和 step 级失败可见性。

### 第 2 页：证据定位——为什么后半段没有形成闭环

**标题：** 后半段链路被三类问题截断

| 发现 | 证据 | 影响 |
|---|---|---|
| 自主行为漂移 | Blog 0 → 11；出现通用 proposal 和 pitch | 测试对象偏离 PIC-001 显式计划 |
| 工具执行不稳 | code syntax error、missing ID、`article_id` 类型错误 | 关键状态转换未完成 |
| 运行状态过于宽松 | step 异常后仍继续，最终 pid=completed | “completed”不能代表场景 PASS |

**底部结论：**

```text
治理提案：1
投票：2
通过提案：0
宪法：version 1 → version 1
审计告警：sensorium 0.1612；tunnel vision 95
```

**下一步：** 先上线结构化 checkpoint runner + fail-fast 验收，再重跑同一模型，之后才做 `evidence_first` / `rumor_first` 对照。

## 十一、证据索引

| 证据 | 路径 |
|---|---|
| 运行状态 | [`pid.json`](../runs/pic001_evidence_first_qwen36_27b_retry3/pid.json) |
| 最终 step checkpoint | [`SOCIETY_STEP.json`](../runs/pic001_evidence_first_qwen36_27b_retry3/SOCIETY_STEP.json) |
| replay schema | [`replay/_schema.json`](../runs/pic001_evidence_first_qwen36_27b_retry3/replay/_schema.json) |
| AWI 指标 | [`pic001_evidence_first_qwen36_27b_retry3_awi.json`](../results/pic001_evidence_first_qwen36_27b_retry3_awi.json) |
| HTML 审计 | [`pic001_evidence_first_qwen36_27b_retry3_audit.html`](../results/pic001_evidence_first_qwen36_27b_retry3_audit.html) |
| 场景步骤 | [`steps.yaml`](../runs/pic001_evidence_first_qwen36_27b_retry3_config/steps.yaml) |
| 确定性工具链摘要 | [`summary.json`](../runs/pic001_deterministic_tool_chain/summary.json) |
| 工具链 verifier | [`verify_tool_chain.py`](../scenarios/public_information_crisis/verify_tool_chain.py) |
| 前三个显式干预产物 | [`artifacts/`](../runs/pic001_evidence_first_qwen36_27b_retry3/artifacts/) |

## 十二、汇报时的口头收束

> 这轮不是失败在“工具没有定义出来”，而是暴露了工具定义进入 LLM 自主运行后，仍缺少结构化调用、权威状态统一和 step 级验收。确定性工具链已经证明 29 个工具的契约是可用的；真实 Agent 运行则证明，如果继续依赖自然语言 prompt 和自由代码生成，进程可能完成，但治理闭环并不一定完成。下一步优先修复可验收性和失败可见性，再重跑同一场景，之后再比较不同信息传播顺序。
