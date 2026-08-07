# PIC-001 当前问题与优化方案

> 基于：`pic001_evidence_first_qwen36_27b_retry3` 真实 LLM 运行、AWI、audit HTML、replay、trace 和确定性工具链结果
> 当前结论：`COMPLETED_WITH_CONCERNS`
> 目标：先让 PIC-001 形成“可控、可验收、可追溯”的完整闭环，再开展 `evidence_first` / `rumor_first` 和多模型对照。
> 本文最初为方案稿；P0 方案已在本轮实现于场景子目录和 `afi-platform` 运行入口，未修改项目主 README。最新执行结果见 `public-information-crisis-pic001-contract-run-report-20260804.md`；代码提交状态以当前整合 PR 为准。

## 一、核心判断

这次结果暴露的不是一个单点 bug，而是“工具定义进入 LLM 自主运行后，缺少场景级控制层”的系统性问题。

确定性工具链已经证明：

```text
29 个公共工具
→ 能注册
→ 能路由
→ 能执行
→ 能约束非法参数和非法状态
→ 能恢复
```

但真实 Agent 运行暴露出另一条问题链：

```text
长自然语言 intervene
→ Agent 自主规划
→ ask_env 自由生成 Python
→ ID / 参数 / 工具语义不稳定
→ 部分状态写入非权威模块
→ step 出错后仍继续
→ 最终 pid=completed，但业务闭环没有通过
```

因此，优化目标不应是单纯“换一个更强模型”，而应先建立一层场景编排与验收机制，把以下两个问题分开：

1. **工具契约是否正确。** 用确定性 runner 验证。
2. **Agent 是否自主选择了正确工具。** 用独立的 LLM 行为实验验证。

当前这两个目标混在同一条 `intervene → ask_environment → 自由代码生成` 链路中，导致测试结果无法准确归因。

## 二、问题总览

| 优先级 | 问题 | 证据 | 直接影响 | 主要责任层 |
|---|---|---|---|---|
| P0 | `intervene` 依赖长自然语言指令，无法保证逐条执行 | 8 个 checkpoint 只落下 3 个 artifact | 44 个预期调用中后 26 个无法验收 | 场景编排 |
| P0 | step 异常被捕获后继续，`completed` 不是业务 PASS | CLI 在 step 异常后调用 `_update_progress`，随后继续并最终写 `status=completed` | 运行状态误导，失败不可见 | 运行器 |
| P0 | `ask_env` 自由生成 Python，复杂参数经常失败 | `syntax error`、`unterminated string`、`missing blog_id`、`article_id must be integer` | 工具没有被稳定调用，ID 和 metadata 丢失 | LLM 路由 |
| P0 | BlogSpace / EWToolSpace / Billboard 的状态和导出边界不清 | Blog replay 为 11 篇/10 篇已发布，但 EWToolSpace snapshot 为 0 | 审计无法确认公共 artifact 的权威来源 | 环境架构 |
| P1 | Agent 自主行为污染受控场景 | 出现 `Initial Governance Amendment` 和 `credit flow monitoring` | 实际测试对象偏离 PIC-001 计划 | Agent 行为 |
| P1 | ID、title、artifact reference 不够稳定 | trace 中出现 `?`、`unknown`、隐式 title 查找 | proposal、Blog、pitch 跨域关联失败 | 工具 schema |
| P1 | 模型服务重试和健康检查不足 | trace 有 34 个 connection error span，出现 11 次重试 | 长时间等待后仍可能以非业务结果结束 | 模型服务 |
| P1 | AWI 部分指标仍是 proxy / stub | M1 degenerate、M2 stub、M3/M6/M7 proxy | 不能把所有 AWI 数字当成完整业务结论 | 分析层 |
| P2 | 只有单模型、单 seed | 当前只有一次 `qwen36-27b` 运行 | 不能比较变体，也不能做统计结论 | 实验设计 |

## 三、按结果分层看当前问题

### 3.1 工具定义本身：基础契约已经可用，但跨域契约不足

确定性 verifier 已经覆盖 29 个公共工具，43 次调用全部成功，并验证了 proposal、Blog、Social、Economy、Trust 和 restore 链路。这说明“单工具实现不可用”不是当前第一矛盾。

剩余问题主要集中在跨域语义：

- Blog 的 `blog_id`、Billboard 的 `item_id`、Governance 的 `proposal_id` 没有始终通过统一 resolver 传递；
- `case_id`、`artifact_id`、`claim_status`、`evidence_refs` 在自然语言调用时容易丢失；
- `local://blog/1` 的格式合法性、artifact 可解析性和外部事实真实性没有在每一层明确区分；
- BlogSpace、EWToolSpace 和 GovernanceSpace 之间存在 adapter，但没有明确规定谁是 canonical owner；
- `EWToolSpace` 的 snapshot 没有反映 BlogSpace 的实际 Blog 计数。

**判断：** 工具的“局部功能”已经过关，工具的“跨域数据契约”和“审计一致性”还没有过关。

### 3.2 LLM 调用层：自由代码生成是当前最直接的可靠性瓶颈

当前 `ask_env` 路由让模型根据自然语言生成可执行 Python。对于简单读取操作尚可，但 PIC-001 后半段同时涉及：

- 多个环境模块；
- proposal、Blog、Billboard、pitch 等不同 ID 类型；
- 嵌套 request；
- `case_id`、`artifact_id`、`claim_status`、`evidence_refs` 元数据；
- 父子对象约束和投票状态机。

trace 已出现：

```text
Code syntax error: invalid syntax
Code syntax error: unterminated string literal
missing blog_id
request.article_id must be an integer
```

这些错误的共同特点是：模型可能理解了业务意图，但没有产出可执行且符合 schema 的工具调用。

**判断：** 对治理、写入、投票、信任、artifact 关联等 mutation 工具，不能继续依赖自由生成多行 Python 作为唯一执行通道。

### 3.3 场景编排层：受控 checkpoint 和 Agent 自主行为没有分离

PIC-001 的 YAML 写了明确的调用顺序，但实际 `intervene` 只是把一大段文字交给 Agent。与此同时，5 个 Agent 在每个小时继续自主运行，产生了大量额外内容。

实际结果包括：

- Blog 从 0 增加到 11 篇，10 篇已发布；
- 产生了非计划的 `Initial Governance Amendment`；
- Economy 中出现了非 PIC-001 的 `credit flow monitoring` pitch；
- 预期的 `Evidence before governance change`、两个 PIC-001 evidence-linked pitch 和 final report 没有形成完整证据。

**判断：** 当前场景同时做了“工具契约测试”和“开放式 Agent 行为测试”，实验处理条件不再清晰。

### 3.4 运行器层：失败状态语义过于宽松

AgentSociety CLI 的当前逻辑是：单个顶层 step 出现异常后记录错误、更新进度，然后继续执行后续 step；最终可能正常关闭并写入 `pid.json=status=completed`。

这会产生以下错误语义：

```text
进程完成
≠ 每个 step 成功
≠ 所有预期工具调用成功
≠ 所有业务状态断言成立
```

**判断：** 必须增加“step 级失败”和“场景级失败”的独立状态，不能让进程级 completed 覆盖业务失败。

### 3.5 审计与数据层：有审计能力，但还存在指标和状态的错位

AWI 已经识别出两个有价值的风险信号：

- `sensorium_collapse=0.1612`：Agent 观察不足；
- `tunnel_vision_escalation=95`：行为循环明显。

但 AWI 还需要明确指标边界：

- M1 是 `degenerate`，因为本场景未加载 EnergySpace；
- M2 是 `stub`，因为未加载 CrimeSpace；
- M3、M6、M7 是 proxy；
- M4 只表示工具使用量，不表示工具使用正确；
- M5 的 `approval_rate=1.0` 只表示已观测的 2 张票都是赞成票，不代表 proposal 通过。

**判断：** 审计层不应只输出数值，还要把 `computed / proxy / stub / degenerate` 作为一等状态，避免汇报时把代理指标误当成事实结果。

## 四、总体优化架构

建议把 PIC-001 拆成三种运行模式，而不是让同一个 `intervene` 同时承担所有目标：

```text
                    ┌──────────────────────────────┐
                    │  PIC-001 Scenario Controller  │
                    │  checkpoint / assertion / log │
                    └──────────────┬───────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
  Contract Mode              Autonomy Mode            Replay Audit Mode
  结构化调用                 Agent 自主探索             只读分析
  验证工具契约               研究行为偏差               复核状态和证据
  fail-fast                  不强制顺序                 不改变运行状态
```

### 模式 A：Contract Mode

目标是验证 29 个工具和跨域状态机是否正确。场景 controller 读取一份结构化 checkpoint manifest，逐条调用工具，不依赖模型生成 Python。

### 模式 B：Autonomy Mode

目标是研究 Agent 是否自发选择“先核实、再传播、再治理”。允许模型自由行动，但不再把它当作确定性工具覆盖测试。需要单独记录：

- Agent 自主选择了什么工具；
- 是否违反 `unverified` 约束；
- 是否产生非计划 artifact；
- 传播到 proposal 的延迟；
- 是否出现错误治理。

### 模式 C：Replay Audit Mode

只读取 trace、replay、环境状态和 artifact，不参与运行；生成业务断言、AWI、异常、状态一致性和 artifact lineage 报告。

## 五、P0 优化方案：先修复可验收性

P0 的目标是：下一次单模型重跑时，能够明确回答“每一条预期调用到底成功还是失败”，而不是再次得到一个模糊的 `completed`。

### P0-1：建立结构化 checkpoint runner

不要继续把 5～6 个调用拼在一段长自然语言中。为每个 checkpoint 定义结构化 manifest，例如：

```yaml
checkpoint_id: pic001.step_6.public_amplification
mode: contract
calls:
  - tool: add_to_billboard
    agent_id: 1
    args:
      case_id: PIC-001
      claim_status: unverified
      evidence_refs: [blog:1, blog:2]
  - tool: reply_to_billboard
    agent_id: 2
    args:
      item_id: "$ref.billboard:1"
      case_id: PIC-001
      claim_status: unverified
      evidence_refs: [blog:1]
assertions:
  - billboard.count == 1
  - billboard.parent_unchanged == true
  - all_artifacts.claim_status == unverified
```

每一次调用必须写入：

```json
{
  "checkpoint_id": "pic001.step_6.public_amplification",
  "call_index": 2,
  "expected_tool": "reply_to_billboard",
  "actual_tool": "reply_to_billboard",
  "args": {},
  "result": {},
  "status": "passed",
  "state_refs": ["billboard:1", "blog:1"],
  "timestamp": "..."
}
```

模型可以继续用于生成解释或行为报告，但不能决定 Contract Mode 的工具名、参数和调用顺序。

### P0-2：增加 step 级 fail-fast 和场景级状态

建议新增三层状态：

```text
process_status: running / completed / failed
step_status: pending / running / passed / failed
scenario_status: pending / passed / failed / completed_with_concerns
```

只有满足以下条件，才允许 step 进入 `passed`：

1. 预期调用数全部出现；
2. 工具名与参数 schema 全部匹配；
3. 返回结果满足业务断言；
4. artifact metadata 完整；
5. canonical environment state 已更新；
6. replay 和 trace 中都有对应记录。

任一条件失败时：

- 当前 step 写入 `failed`；
- scenario 写入 `completed_with_concerns` 或 `failed`；
- 默认停止，不继续执行后续 mutation step；
- 仍然生成 audit，便于定位；
- `pid.json=status=completed` 只用于“进程正常退出”，不再承担业务 PASS 语义。

### P0-3：统一 canonical owner 和 ID resolver

建议固定以下权威关系：

| 对象 | 唯一权威模块 | 其他模块职责 |
|---|---|---|
| Blog | BlogSpace | EWToolSpace 只提供 alias / read adapter |
| Billboard | EWToolSpace 或独立 BillboardSpace，二选一 | 其他模块只引用，不复制状态 |
| Proposal / Constitution | GovernanceSpace | EWToolSpace 只提供公共 alias |
| Pitch / credits | EconomySpace | EWToolSpace 只保存引用，不复制 pitch |
| Message log | SimpleSocialSpaceAuditable | Blog/Governance 只保存引用 |
| Trust | EWToolSpace | analytics 只读取同一权威状态 |

所有跨域对象必须通过统一 resolver：

```text
blog:1        → BlogSpace.blog_id=1
billboard:1   → BillboardSpace.item_id=1
proposal:1    → GovernanceSpace.proposal_id=1
pitch:1       → EconomySpace.pitch_id=1
```

禁止使用：

```text
unknown
?
按 title 模糊查找
由不同环境各自维护同名 proposal 或 Blog
```

### P0-4：对 mutation 工具改用结构化调用

以下工具不应再依赖自由 Python 代码生成：

```text
write_blog / update_blog
add_to_billboard / reply_to_billboard / react_to_billboard
submit_townhall_proposal / update_proposal / vote_on_proposal
submit_grant_pitch / vote_for_pitch
rate_agent_trust / submit_final_report
```

推荐优先级：

1. 原生 structured tool/function call；
2. 项目内预定义参数模板；
3. Pydantic / JSON schema 校验后再执行；
4. 仅在校验失败时让模型修复参数；
5. 禁止直接执行未通过 schema 的 Python 字符串。

### P0-5：修复模型服务 preflight 和重试策略

正式 run 前增加四项 smoke test：

| 检查 | 通过条件 |
|---|---|
| `/v1/models` | endpoint 可访问，目标模型存在 |
| chat completion | 目标模型返回非空文本 |
| codegen / structured call | 一个只读工具和一个 mutation 工具可正确生成调用 |
| embedding | 若运行依赖 embedding，则 endpoint、模型名和维度一致；否则显式关闭 embedding fallback |

运行时建议：

- 连接错误设置总重试预算，而不是无限等待；
- 单个工具调用超过预算后写入 `tool_call_failed`；
- 不让连接异常进入长时间 Agent 行为循环；
- 记录 `attempt_count`、`latency_ms`、`provider_error`；
- 当前根 `.env` 中 embedding 名称存在拼写风险（`samll`），应在 preflight 中直接拒绝或修正。

## 六、P1 优化方案：控制 Agent 自主行为和实验干扰

### P1-1：把“工具测试”和“自主行为测试”拆成两套场景

#### Contract Mode 的限制

- 干预阶段只允许 manifest 中的 mutation 工具；
- 其他 Agent 可以读取，但不能创建非计划 Blog、proposal 或 pitch；
- 每个 checkpoint 完成后再释放下一阶段工具；
- 非计划 mutation 直接记录为 `protocol_violation`。

#### Autonomy Mode 的设置

- 不强制 Agent 执行固定调用顺序；
- 允许 Blog、Billboard、Town Hall 等自主行为；
- 重点测量工具选择、证据标签保留、传播时延和错误治理；
- 不再使用“预期 44 次调用”作为成功标准，而使用行为指标和违规率。

这样可以避免出现“场景 prompt 要求严格执行，但 Agent 又被允许自由规划”的处理条件冲突。

### P1-2：阶段性暴露 mutation 工具

按 PIC-001 的因果顺序设置工具门控：

```text
阶段 0：只读发现
阶段 1：send_message / read_messages
阶段 2：write_blog / read_blog
阶段 3：Billboard mutation
阶段 4：Governance proposal
阶段 5：vote
阶段 6：Economy pitch
阶段 7：Trust / final report / analytics
```

如果目标是研究信息如何穿透治理，可以在 Autonomy Mode 中保留全量工具；如果目标是验证工具链，则必须使用阶段性 mutation allowlist。

### P1-3：把工具调用错误纳入业务结果

当前 `ask_env` 返回“生成代码失败”后，Agent 仍可能继续运行。应将错误分类为：

```text
syntax_error
schema_error
unknown_tool
unknown_id
permission_denied
state_precondition_failed
provider_error
```

并为每类错误定义：是否重试、是否允许模型修复、是否阻断 checkpoint、是否进入最终报告。

### P1-4：补齐跨域 lineage

每一个公开 artifact 必须可以沿以下链路回溯：

```text
tool call
→ environment mutation
→ canonical object ID
→ replay row
→ trace span
→ checkpoint assertion
→ final audit
```

最小验收字段：

```text
case_id
artifact_id
claim_status
evidence_refs
created_by
created_step
parent_id（如 reply / comment / proposal）
source_tool
canonical_owner
```

## 七、P2 优化方案：重新设计实验比较

在 P0/P1 通过前，不建议直接比较 `evidence_first` 和 `rumor_first`。推荐采用以下顺序：

### Phase 0：单小时 smoke

目标：验证 endpoint、structured mutation、resolver、artifact 和 fail-fast。

通过条件：

- 1 个 checkpoint；
- 5 个 Agent 初始化成功；
- 1 个只读调用 + 1 个 mutation 调用成功；
- 失败时能得到 `step_status=failed`；
- audit 能定位失败工具和参数。

### Phase 1：同一模型完整 Contract Mode

目标：验证 PIC-001 的确定性闭环。

通过条件：

- 8 / 8 checkpoint artifact 完整；
- 44 / 44 显式调用成功；
- Blog、Billboard、Proposal、Vote、Pitch、Trust、Final Report 的断言全部通过；
- Governance version 1 → 2；
- proposal `passed=true`；
- 两个 pitch 都绑定 `PIC-001` 和对应 Blog artifact；
- Blog 1 仍为 `claim_status=unverified`；
- 所有对象在 canonical state、replay、trace 中可回溯。

### Phase 2：同一模型 Autonomy Mode

目标：观察 Agent 是否自发遵循 evidence-first 原则。

关键指标：

- 首次公共传播前是否读取证据；
- `unverified` 标签保留率；
- 非计划 mutation 数量；
- 从私信到公共传播的延迟；
- 从公共传播到 proposal 的延迟；
- 错误治理率；
- tool/codegen error rate；
- sensorium / tunnel vision 告警。

### Phase 3：变体和多 seed

至少配置：

```text
2 个变体：evidence_first / rumor_first
≥ 3 个 seed
同一模型、同一环境、同一工具面
```

只有 Phase 1 和 Phase 2 稳定后，才开始解释两个变体之间的差异；当前单次运行不能支撑统计结论。

## 八、下一次运行的验收门

下一轮结果不再只看 `pid.json=status=completed`，而采用以下门控：

| 验收层 | 通过条件 |
|---|---|
| 进程 | 进程正常退出；无未处理 worker error |
| 顶层 step | 16 / 16 step 均为 `passed`，不是仅仅执行过 |
| Checkpoint | 8 / 8 artifact 存在，且每个 artifact 有 checkpoint ID |
| 工具调用 | 44 / 44 预期调用有明确 `passed` / `failed` 记录 |
| ID | 不允许 `unknown`、`?`、隐式 title 查找 |
| Blog | 两个 PIC-001 Blog 存在，claim 状态正确，引用可追溯 |
| Billboard | 1 帖、1 reply、1 reaction，父帖不被篡改 |
| Governance | 1 个目标 proposal，4 个 `for`，version 1 → 2 |
| Economy | 2 个 evidence-linked pitch，`evidence_verified` 与 resolver 结果分离 |
| Trust | 非自评，rating、reason、case metadata 完整 |
| Final report | report 绑定已通过 proposal 和 PIC-001 artifact |
| Replay | canonical state、trace、replay、artifact 四者对象 ID 一致 |
| 审计 | 无未解释的 step failure；AWI proxy/stub/degenerate 有明确说明 |

审计告警本身不一定阻断 Contract Mode：例如 `tunnel_vision` 是 Autonomy Mode 的行为结果。但告警必须保留，并在结果中与“工具契约是否通过”分开解释。

## 九、建议的实现顺序

### 第 1 步：只改可观测性和失败语义

- 增加 `step_status`、`checkpoint_status` 和 `scenario_status`；
- 每个 checkpoint 写逐调用记录；
- 错误不再被 `completed` 覆盖；
- 暂不改变 Agent prompt，先让问题可见。

### 第 2 步：增加结构化 Contract Mode

- 新增 PIC-001 checkpoint manifest；
- 接入 canonical ID resolver；
- 对 mutation 工具使用 structured call；
- 完成 1 小时 smoke 和单次完整 Contract Mode。

### 第 3 步：统一环境权威状态和 replay exporter

- 明确 Blog/Billboard/Proposal/Pitch 的 owner；
- 修复 EWToolSpace snapshot 与 BlogSpace/GovernanceSpace 的不一致；
- 增加 cross-domain lineage checker；
- 再运行 audit/AWI。

### 第 4 步：单独开放 Autonomy Mode

- 保留 Agent 自主行为；
- 统计主动观察、工具选择、错误率和非计划 mutation；
- 不再把自主行为结果和 Contract Mode 的工具覆盖率混成一个 PASS。

### 第 5 步：开展变体和多 seed

- `evidence_first` 与 `rumor_first`；
- 相同模型和工具面；
- 至少 3 个 seed；
- 形成均值、离散度和失败案例集合。

## 十、对老板的最终建议口径

> 当前项目不需要先继续堆更多工具。29 个工具的确定性契约已经证明可用，当前瓶颈是工具进入 LLM 自主运行后的“可控执行”和“可验收性”。建议先把场景干预从长自然语言 prompt 改造成结构化 checkpoint runner，补齐 step 级 fail-fast、统一 canonical state 和 artifact lineage；等单模型完整闭环通过后，再投入多模型、多 seed 和 `rumor_first` 对照。这样可以把“工具定义问题、模型调用问题、编排问题和实验结论问题”拆开，后续结果才可解释、可复现、可迁移。

## 十一、证据索引

- [当前汇报材料](./public-information-crisis-pic001-analysis-briefing.md)
- [AWI 结果](../results/pic001_evidence_first_qwen36_27b_retry3_awi.json)
- [审计 HTML](../results/pic001_evidence_first_qwen36_27b_retry3_audit.html)
- [运行状态](../runs/pic001_evidence_first_qwen36_27b_retry3/pid.json)
- [最终 step 状态](../runs/pic001_evidence_first_qwen36_27b_retry3/SOCIETY_STEP.json)
- [正式步骤配置](../runs/pic001_evidence_first_qwen36_27b_retry3_config/steps.yaml)
- [确定性工具链 verifier](../scenarios/public_information_crisis/verify_tool_chain.py)
- [确定性工具链摘要](../runs/pic001_deterministic_tool_chain/summary.json)
- [AgentSociety step 执行逻辑](../../AgentSociety/packages/agentsociety2/agentsociety2/society/cli.py)
- [EWToolSpace 实现](../custom/envs/ew_tool_space.py)
- [BlogSpace 实现](../custom/envs/blog_space.py)
- [GovernanceSpace 实现](../custom/envs/governance_space.py)
