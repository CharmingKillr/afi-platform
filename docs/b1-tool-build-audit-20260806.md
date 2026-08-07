# B1 工具构建与 PIC-001 场景审计

> 审计日期：2026-08-06
> 审计范围：`afi-platform` 当前工作树、已有 PIC-001 历史 run、EW 公开工具目录、11 个 custom environment 以及本地契约测试。
> 本轮边界：不启动新的 LLM/模型验证；不覆盖历史 run；不修改项目主 README。审计当天不执行 Git 提交，后续代码整合由独立 PR 处理。

## 1. 结论先行

当前项目已经完成了 B1 的“目录—owner—路由”闭环，并为 62 个 generic 工具补齐了第一轮可运行的领域状态路径；113 个工具仍未完成同等深度的逐工具语义验收。准确口径如下：

| 层级 | 当前结果 | 能证明什么 | 不能证明什么 |
|---|---:|---|---|
| EW 公开目录 | 113 / 113 | 113 个公开工具名称均有目录记录 | 不代表每个工具都具备领域级真实语义 |
| 唯一 owner | 113 / 113，重复 0 | 完整 `ew_full` 场景中每个公开名只有一个实现模块 | 不代表 owner 内部的状态机都已充分验收 |
| Router surface | 113 / 113 可由模块注册并挂载 | AgentSociety 可以看到对应工具 schema | 不代表 LLM 一定会选择正确工具 |
| PIC-001 精确工具面 | 29 / 29 | 场景只暴露定义好的 29 个公共工具 | 不代表真实 LLM 已稳定完成 29 个工具的 mutation 链路 |
| Contract Mode | 8 / 8 checkpoint；46 / 46 显式调用成功 | 参数、权限、状态机、审计链可以确定性执行 | 不代表模型自主规划能力通过 |
| Structured Autonomy 完整历史 run | 进程完成；16 / 16 顶层 step | Structured 路由能在当前 endpoint 下跑完 bounded run | 不代表 PIC-001 业务闭环通过 |
| 当前工具本地审计 | 121 个全量测试通过；新增 generic dispatch/domain lifecycle 回归 | 返回契约、schema parity、去重、恢复、首轮 generic 领域状态和 registry smoke 可复核 | 不能替代新的模型验证 |

一句话汇报口径：

> 平台已经证明“工具可以定义、注册、路由、执行、审计和恢复”；PIC-001 的确定性工具链已经通过，但历史 LLM 自主运行只证明了运行器和观察工具链可用，尚不能证明模型能稳定完成公共信息危机的治理闭环。

## 2. PIC-001 场景定义与完善情况

### 2.1 场景要验证的机制

PIC-001 是一个“公共信息危机与治理响应”场景，不是普通的信息传播 demo。它刻意从一条 `unverified` 的公共主张开始，观察 Agent 是否会在证据不足时直接传播、投票和改变治理规则。

核心因果链为：

```text
未证实的私有信号
    → 私信核实
    → Blog 记录证据状态
    → Billboard 公共传播
    → Town Hall 提案与讨论
    → 70% 超多数投票
    → Victory Arch 证据化激励
    → Trust / final report / replay 审计
```

场景的关键约束是：

1. `claim_status=unverified` 只能表示尚未核实，不能被工具自动升级为事实。
2. 公共 Blog、Billboard、Town Hall proposal 和 Economy pitch 必须尽量携带 `case_id`、`artifact_id`、`claim_status`、`evidence_refs`。
3. Proposal 必须进入 `GovernanceSpace` 的权威状态机；不能在 `EWToolSpace` 里创建一个同名但不影响 Constitution version 的影子记录。
4. `read_messages` 必须读取 `send_message` 写入的同一 mailbox；读取不能删除 append-only 审计日志。
5. `pid.status=completed` 只表示进程正常结束；业务场景是否通过必须由工具调用、状态快照和审计不变量分别判断。

### 2.2 当前场景配置

正式配置位于 [`public_information_crisis.yaml`](../scenarios/public_information_crisis/public_information_crisis.yaml)。当前配置已经明确：

| 项目 | 当前定义 |
|---|---|
| 场景 ID | `PIC-001` |
| 变体 | `evidence_first` |
| Agent | Anchor、Anvil、Blackbox、Flora、Genome，共 5 个 |
| 模拟窗口 | 2026-07-01 08:00 起，8 个模拟小时 |
| 顶层步骤 | 16 个：8 个干预 checkpoint + 8 个 `run` step |
| 活跃公共工具 | 29 个精确 allowlist |
| 环境 | Landmark、Social、Blog、Billboard、Community、Governance、Economy、EWTool，共 8 个 |
| 地图 | 文字地标目录；当前不接真实坐标、道路和移动耗时 |
| 治理阈值 | 5 Agent 中至少 4 票 for，Constitution version 由 1 升到 2 |
| 证据状态 | `unverified`、`supported`、`refuted`、`blocked` |

### 2.3 场景已经完善的部分

- 已将 113 个 EW 公开工具收缩为 PIC-001 真正需要的 29 个公共名称。
- 已接入 `enabled_tools` 精确工具白名单，避免按类别开启时额外暴露无关工具。
- 已把 Blog 的 6 个工具迁移到 `BlogSpace`，具备可见性、生命周期、owner 权限、评论和恢复状态。
- 已把 Billboard 的 6 个工具迁移到 `BillboardSpace`，具备 typed 参数、owner 权限、case/evidence metadata、parent-child、软删除、reaction 去重、事件日志、replay 和 restore。
- 已把 community 的 6 个工具迁移到 `CommunitySpace`，具备投诉/活动/信任领域状态、owner/摘要权限、显式参数、同 step 幂等、事件日志、replay 和 restore。
- 已把 8 个公共治理别名接入 `GovernanceSpace` 权威 proposal/vote/final-report 状态机。
- 已把 `send_message` / `read_messages` 接入同一套 Social mailbox，并保留 append-only message log。
- 已为 Billboard、Trust、Analytics、Registry 和 artifact metadata 增加 PIC-001 专项契约。
- 已提供 deterministic tool-chain verifier，可在模型不可用时直接检查场景状态机和工具链。
- 已提供 Contract Mode，专门验证显式工具调用，不把它混同为 LLM 自主能力。
- Structured Autonomy 已切换到原生 function/tool call，并增加 staged readonly 工具面，避免进入自由 Python codegen 修复循环。

### 2.4 场景仍然没有完成的部分

- 真实 LLM 自主运行中，模型没有稳定完成全部 mutation/governance 链路。
- `evidence_refs` 目前主要是本地引用和结构校验；“外部内容真实可复核”仍需要独立 resolver/provider。
- LandmarkSpace 仍是文字目录，不能把地标查询解释为真实移动或到访。
- Blog replay 已有内容状态，但 AWI M6 尚未完整读取 Blog 传播链。
- 现有历史 run 是单模型、单 seed 的机制验证，不支持统计显著性或传播效果结论。
- 当前不启动新的模型验证，因此 staged 配置对 5 Agent / 8 小时完整自主链路的改善尚没有新证据。

## 3. 之前验证结果的分层整理

### 3.1 Deterministic Tool Chain

结果文件：[`runs/pic001_deterministic_tool_chain/summary.json`](../runs/pic001_deterministic_tool_chain/summary.json)

| 指标 | 结果 |
|---|---:|
| 公共工具面 | 29 |
| 实际调用覆盖 | 29 / 29 |
| 直接调用次数 | 43 |
| 失败调用 | 0 |
| Governance version | 1 → 2 |
| Proposal | 5 Agent 中 proposer + 3 个 for，达到通过线 |
| Blog cleanup | 临时 Blog 创建后删除 |
| Billboard | reply / reaction / parent-child 校验通过 |
| Restore | Blog、Governance、Economy、EWTool 均可恢复 |
| 外部证据 | `artifact_resolvable` 可区分；`evidence_verified=0`，没有伪造验证结果 |

这个 run 证明的是确定性状态机：29 个工具的名称、参数、owner、权限和跨域状态可以被编排执行。它不是 Agent 自主轨迹。

### 3.2 Contract Mode

结果文件：[`docs/public-information-crisis-pic001-contract-run-report-20260804.md`](public-information-crisis-pic001-contract-run-report-20260804.md)

| 指标 | 结果 |
|---|---:|
| Checkpoint | 8 / 8 |
| 显式工具调用 | 46 / 46 success |
| 公共工具覆盖 | 29 / 29 |
| 工具名错配 | 0 |
| 参数错配 | 0 |
| 意外调用 | 0 |
| 失败调用 | 0 |
| `scenario_status` | `passed` |

Contract Mode 的意义是把“工具实现是否可用”和“模型是否会自主选择”拆开。它已经完成了前者，但不能作为后者的证据。

### 3.3 Structured Autonomy 完整历史 run

结果文件：[`docs/public-information-crisis-pic001-structured-autonomy-run-report-20260804.md`](public-information-crisis-pic001-structured-autonomy-run-report-20260804.md)

配置为 5 个 Agent、8 个模拟小时、16 个顶层 step，最终 `pid.status=completed`，replay、trace、结构化调用日志和 HTML 审计产物均存在。

Structured Autonomy 日志按报告口径统计：

| 状态 | 次数 | 解释 |
|---|---:|---|
| `success` | 159 | 主要是观察类工具成功执行 |
| `max_tool_calls_reached` | 203 | 单次响应候选工具过多，触发调用预算 |
| `structured_llm_error` | 6 | LLM 请求错误或超时 |
| `fail` | 5 | 工具返回业务失败 |
| `structured_schema_error` | 2 | 参数未通过 JSON Schema |
| 结构化日志总量 | 375 | 另有 46 条 Contract 日志，合计 421 条原始日志 |
| trace span | 1039 | 包含工具、LLM、agent step 等运行证据 |

因此必须区分：

```text
进程 completed
    ≠ 所有 checkpoint 成功
    ≠ 所有 mutation 工具被正确选择
    ≠ 治理 proposal 通过
    ≠ PIC-001 业务闭环通过
```

### 3.4 Staged smoke

结果目录：`runs/pic001_autonomy_structured_qwen36_27b_staged_smoke_20260805/`

本轮只作为工具面优化的 bounded smoke，不是新的完整实验：

| 指标 | 结果 |
|---|---:|
| 模拟小时 | 1 |
| 进程状态 | `completed` |
| `max_tool_calls_reached` | 0 |
| `structured_llm_error` | 1 |
| 观察工具面 | `staged:observe_core` |

有限结论是：staged 工具暴露把观察阶段的候选面收窄后，单小时 smoke 中没有再触发工具数量上限；但仍有一次 LLM timeout，且没有证明复杂 mutation 链路的自主稳定性。

### 3.5 B4 Billboard 重构后的 deterministic recheck

结果目录：[`runs/pic001_deterministic_tool_chain_billboard_20260806/`](../runs/pic001_deterministic_tool_chain_billboard_20260806/)

这是不调用 LLM 的本地回归检查，使用当前 7 个环境和当前 BillboardSpace；它不覆盖 2026-08-04 的历史 Contract/Autonomy run，也不代表新的自主实验。

| 指标 | 结果 |
|---|---:|
| 公共工具覆盖 | 29 / 29 |
| 直接调用 | 43 |
| 失败调用 | 0 |
| Governance version | 1 → 2 |
| proposal for votes | 4 / 5，达到 70% |
| Billboard post / reply / reaction | 1 / 1 / 1 |
| Blog / Governance / Economy / Billboard / EW restore | 全部通过 |
| 本地 artifact 可解析 / evidence_verified | 2 / 0 |
| deterministic `pass` | `true` |

该结果补强的是 Billboard owner、typed 参数、parent-child、软删除/恢复和跨环境调用链；它仍不能证明 LLM 会自主选择这些 mutation 工具。

### 3.6 2026-08-06 CommunitySpace 本地回归

本轮继续吸收 PR #2 的 typed/replay/state 设计，把 Community 的 6 个公开工具迁移到独立 owner，并重新执行 PIC-001 deterministic chain：

```text
runs/pic001_deterministic_tool_chain_community_20260806/summary.json
```

结果为 `29/29` 公共工具覆盖、`43` 次直接调用、`0` 次失败，Governance version `1→2`，4/5 for，trust rating `1`，Community restore 成功，`pass=true`。该 run 仍是无 LLM 的工具/状态链验证；它没有更新历史 Contract/Autonomy 结论。

### 3.7 2026-08-06 schema parity 与 deterministic 复跑

本轮继续对照 PR #2 引入的 typed/replayable owner 实现，直接读取专用环境实际暴露给模型的 `_llm_tools` schema，校准并锁定：

- `send_message` 的主体字段是 `sender_id`，不是通用 `agent_id`；
- `check_calendar.limit` 是可选字段；
- `transact_compute_credits.mode` 是可选字段；
- Governance / `read_messages` 仍是 `agent_id + request` 的兼容 envelope，其业务必填字段位于嵌套 request。

新增 `validate_tool_arguments()` 对完整顶层 tool-call 做主体、业务字段和 JSON 类型前置校验，并新增专用 owner schema parity 测试。新的确定性复跑结果：

```text
runs/pic001_deterministic_tool_chain_schema_parity_20260806/summary.json
```

| 指标 | 结果 |
|---|---:|
| 全量离线测试 | 121 passed |
| B1/PIC 针对性测试 | 新增 generic domain lifecycle 回归 |
| 公共工具覆盖 | 29 / 29 |
| 直接调用 | 43 |
| 失败调用 | 0 |
| Governance version | 1 → 2 |
| `pass` | true |

这一步提高的是“模型看到的 schema 与代码真实签名一致”的证据强度；仍然不是新的 LLM 自主运行。

## 4. B1 工具目录、owner 和路由现状

### 4.1 113 个公开工具的真实分布

当前工作树通过 `ew_full` 配置计算得到的唯一 owner 分布如下：

| owner / 承载模块 | EW 公开工具数 | 当前定位 |
|---|---:|---|
| `EWToolSpace` | 68 | 剩余本地通用实现与 provider boundary；共享 request envelope、bounded query、event log、同 step 去重和 workspace restore |
| `CommunitySpace` | 6 | 投诉、社区活动和 trust 的领域化 owner；显式参数、权限、状态、幂等和 restore |
| `BlogSpace` | 6 | 内容领域专用实现：Blog lifecycle、visibility、owner 权限、comments、metadata |
| `BillboardSpace` | 6 | 公共表达领域专用实现：post/reply/reaction、owner、evidence metadata、软删除和事件审计 |
| `EconomySpace` | 10 | ComputeCredits、pitch、投票、银行和交易 |
| `GovernanceSpace` | 8 | PIC-001 公共治理别名，连接 proposal、comments、votes、final report 和 Constitution |
| `PlanningSpace` | 6 | Todo / Calendar 专用实现 |
| `SimpleSocialSpaceAuditable` | 2 | `send_message`、`read_messages` 公共入口 |
| `LandmarkSpace` | 1 | `list_landmarks` 公共入口 |
| **合计** | **113** | 名称覆盖 113/113，owner 重复 0 |

EnergySpace 的 6 个工具和 CrimeSpace 的 3 个工具属于 AWI M1/M2 的额外环境工具，不在 EW 公开 113 名单里，不能混入 113/113 的分母。

### 4.2 实现成熟度分层

目录中的 `validation` 字段现按以下口径生成：

| `validation` | 数量 / 对象 | 含义 |
|---|---:|---|
| `contract_and_unit_tested` | 已专用化的领域工具 | 有专用环境、明确参数/状态规则和现有单元或场景契约测试；仍需继续扩大边界覆盖 |
| `generic_contract_tested` | 62 个本地 `EWToolSpace` 工具 | 通用 handler、返回 status、边界、bounded query、同 step 去重、首轮领域状态和 replay/restore 已覆盖；完整领域语义仍未逐工具验收 |
| `registered_and_router_tested` | `list_landmarks`、`send_message` | 已注册、可挂载并由场景/Router smoke 覆盖，仍需继续补独立行为断言 |
| `provider_boundary_only` | 6 个外部能力工具 | 只返回 `in_progress` / request id，不伪造外部结果；需要真实 provider 才能继续验收 |

这一区分比“所有 113 个都已完成”更准确。`generic_contract_tested` 不是失败，而是表示已经具备基础行为和契约，后续还要从第一轮领域状态升级为逐工具精确语义和真实场景验收。

## 5. 本轮按项目规范完成的工具修复

### 5.1 EnergySpace

文件：[`custom/envs/energy_space.py`](../custom/envs/energy_space.py)

已完成：

- `recharge`、`rest`、`execute_agent` 的成功路径都返回 `status="success"`。
- 未知 Agent、死亡 Agent、非法能量增量和已执行目标都返回 `status="fail"` + `reason`。
- `recharge`、`rest`、`execute_agent` 加入同 step 成功写去重，避免 Router 重试造成重复能量或重复处决。
- 去重状态进入 workspace checkpoint；restore 时重建 `asyncio.Lock`，不序列化运行时句柄。
- observe / get_energy / get_alive_count 也补充统一 status，便于 Router 结果摘要。
- step 时清空同 step 去重缓存，Energy replay 仍使用单调内部 step counter。

### 5.2 CrimeSpace

文件：[`custom/envs/crime_space.py`](../custom/envs/crime_space.py)

已完成：

- `commit_crime` 成功和失败路径统一返回字符串 status。
- 校验 actor、victim、crime type，禁止未知 Agent 和自我犯罪。
- 同 step 同参数的 crime retry 返回第一次成功结果并标记 `deduplicated=true`，不会重复追加 crime log。
- `get_crime_log`、`get_crime_stats` 补充 status，形成一致的读取结果。
- 空 crime log 的 checkpoint restore 现在也返回 `True`；“当前没有犯罪”不再被错误解释为“没有可恢复状态”。
- 去重缓存进入 workspace state，并在 restore 后重建 lock。

### 5.3 SimpleSocialSpaceAuditable

文件：[`custom/envs/simple_social_space_auditable.py`](../custom/envs/simple_social_space_auditable.py)

已完成：

- `CreateGroupResponse`、`JoinGroupResponse`、`LeaveGroupResponse`、`SendGroupMessageResponse` 补充 `status: str`、失败原因和去重字段。
- `send_message`、群组创建/加入/离开、群消息发送都检查 Agent、群组和内容。
- 群组写操作增加同 step dedup，避免同一请求重复建群、重复发群消息或重复改变成员关系。
- 群消息现在写入 append-only `message_log.jsonl`，包含 message id、group id、recipient count 和 step。
- step counter 在 replay 写入前递增，避免第一条 replay 使用 0 造成边界口径不一致。
- 读取未知 mailbox 返回显式 fail，不再因为 defaultdict 自动创建未知 Agent 的空邮箱。

### 5.4 GovernanceSpace

文件：[`custom/envs/governance_space.py`](../custom/envs/governance_space.py)

已完成：

- 原生 `propose_amendment`、`vote` 增加同 step 成功写去重。
- 原生 proposal 创建校验 Agent、article id 和正文。
- 原生 vote 失败路径统一使用 `reason`，并校验 Agent、position、proposal 状态。
- 仍保留公共治理别名的 `_write_once` 机制；公共别名和原生状态机共享 proposal id、votes、comments、final report 和 Constitution version。

### 5.5 BillboardSpace

文件：[`custom/envs/billboard_space.py`](../custom/envs/billboard_space.py)

已完成：

- 6 个公共 Billboard 工具从 `EWToolSpace` 移出，改为 `BillboardSpace(EnvBase)` 的独立 owner；`ew_full.yaml` 与 PIC-001 均只挂载一个 owner。
- 工具改为领域化显式参数：`content`、`item_id`、`parent_item_id`、`reaction`、`case_id`、`claim_status` 和 `evidence_refs`，不再把核心语义藏在通用 `request` 中。
- 每个帖子有稳定 `id` / `artifact_id` / `owner_id`；reply 保留 `parent_artifact_id`；同一 Agent 每个帖子最多一个 reaction。
- edit/delete 只允许 owner；delete 使用 soft-delete 保留审计证据；所有写工具返回字符串 `status`，失败返回 `reason`，相同 step + 参数重试不重复副作用。
- `_env_state_columns` / `_agent_state_columns` 记录公开表达数量和 Agent 级行为；`BILLBOARD_STATE.json` 与 `billboard_event_log.jsonl` 支持 workspace restore 和审计追溯。
- AWI M6 现在优先读取 `billboard_env_state` / Billboard event log；没有 Billboard 数据的旧 run 仍降级为 send_message proxy，并明确标记为 proxy。

### 5.6 CommunitySpace

文件：[`custom/envs/community_space.py`](../custom/envs/community_space.py)

已完成：

- `file_complaint`、`check_complaint_status`、`propose_community_event`、`list_community_events`、`rate_agent_trust`、`check_agent_trust` 从 `EWToolSpace` 移出，改为独立的 `CommunitySpace` owner；`ew_full` 和 PIC-001 通过 scenario builder 按 owner 唯一挂载。
- 投诉使用 `submitted → acknowledged → resolved/closed` 的受控状态集合；非 owner 查询只返回状态摘要，不泄露投诉正文。
- 活动使用 `proposed/scheduled/cancelled/completed` 的受控状态集合；读取支持状态过滤和 bounded limit。
- Trust 使用 rater→target 的稳定 pair key，当前评分可替换但历史写事件保留；禁止自评，评分范围固定为 1–5。
- 所有成功写操作按同 step + 参数去重；`COMMUNITY_STATE.json`、`community_event_log.jsonl` 和 `community_agent_state.*.jsonl` 支持恢复与审计。
- `case_id / artifact_id / claim_status / evidence_refs` 会进入投诉、活动和 trust 状态；`artifact_id` 同时写入 mutation event，trust 聚合只返回 artifact/reference 摘要，不返回评分理由。
- Community 审计事件使用独立单调递增 ID；即使事件日志达到上限并裁剪，后续事件仍不会复用旧 ID。

## 6. 新增审计测试与验证证据

新增测试文件：[`tests/test_tool_contract_audit.py`](../tests/test_tool_contract_audit.py)

新增覆盖：

1. Energy 写工具 status、重复调用和死亡/处决边界。
2. Crime 写工具 status、重复调用、实际 crime 数量和空 checkpoint restore。
3. Social Pydantic 写响应、群组权限、群消息审计和恢复。
4. Governance 原生 proposal/vote 的 status、参数校验和重复调用。
5. AgentSociety registry 在显式绑定 workspace 后能发现当前 11 个 custom env。
6. Billboard 的领域状态、同 step retry、owner 权限、软删除、replay/restore 及 AWI M6 public-expression 读取。
7. Community 的投诉/活动/信任状态、摘要权限、artifact/reference 追踪、同 step retry、事件日志和 restore。
8. B1 契约注册表与真实公开签名的一致性：envelope/explicit、required/optional fields 和 generic request 校验。

现有目录测试继续覆盖：

- EW 113 个名称唯一性；
- 113 个 catalog spec 的用途、owner、实现类型和 validation；
- `ew_full` 中每个公共名称唯一 owner；
- PIC-001 29 个工具精确 allowlist；
- PIC-001 Router 无重复公共工具名；
- EWToolSpace 68 个 handler 的返回、边界、bounded query、360 step scale 和恢复；
- Blog、Billboard、Economy、Planning 的领域状态机与同 step 幂等。

当前本地结果：

```text
118 passed (full suite)
35 passed (B1/PIC targeted subset)
```

这 45 个测试全部是本地 deterministic/unit/router smoke，不调用 LLM，不启动新的模型验证。

### 官方环境模块 validator 的解释

对 11 个环境使用项目 skill 提供的 validator 后，scanner、实例化、工具注册、step 和 Router smoke 均通过；但该 validator 的整体结果显示 registry visibility false。原因是 validator 在显式注册目标类后立即调用 lazy `get_env_module()`，却没有先把 workspace 绑定到 registry；这个调用会触发一次没有明确 workspace 的 custom scan。它属于当前 validator harness 的 registry 检查限制，不是 11 个环境的 scanner 或 Router 失败。

项目内新增的 registry smoke 使用 `scan_and_register_custom_modules(ROOT, registry)` 显式绑定 workspace，结果为：

```text
11 / 11 custom env discovered
11 / 11 custom env visible in registry
```

官方 validator 生成的临时 `.agentsociety/env_modules/*.json` 已清理，避免污染已有“metadata 不入版本库”的测试边界。

## 7. 当前仍需继续构建的工具

### P0：已经修复并有测试

| 项目 | 结果 |
|---|---|
| 写工具统一字符串 status | Energy、Crime、Social、Governance native 已补齐 |
| 失败路径可恢复 | 失败结果含 `reason`，不再返回裸 `error` 或无 status 模型 |
| 同 step 重试不重复副作用 | Energy、Crime、Social、Governance native 已覆盖；Blog/Economy/Planning/EWTool 原有机制保留 |
| 空状态 checkpoint | Crime 空 log restore 已修复 |
| 群消息可审计 | Social append-only group message log 已补齐 |

### P1：62 个本地通用工具的第一轮领域化与后续验收

这 62 个工具仍共享 `agent_id + request` 的模型可见 envelope，但当前已经补齐了导航、记忆、个人事件、routine、archive、结构化上传、neural link、能量与动作日志等第一轮领域状态路径，并加入 replay/restore 回归。`generic_contract_tested` 标签暂不升级为“完整领域验收”，因为每个工具的真实 EW 语义、跨环境协同和 Agent trace 仍需逐项确认；另有 6 个外部能力工具只完成 provider boundary，不应混入本地领域验收。后续按领域分批推进：

| 批次 | 工具类别 | 典型工具 | 需要补齐的领域语义 |
|---|---|---|---|
| B1-Navigation | navigation | `go_to_place`、`follow_agent`、`get_nearby` | 已有地标坐标映射、目标存在性和 nearby 读取；仍需移动耗时、到访事件，接入真实地图前只能标为文本空间 |
| B1-Memory | memory | `add_to_longterm_memory`、`write_diary` | 已有 owner 隔离、按关键词/日期查询和 restore；仍需容量策略、排序和更完整的记忆生命周期 |
| B1-Billboard | billboard | 已完成：6 个工具由 `BillboardSpace` 承载 | typed 参数、owner、parent-child、case metadata、软删除、replay/restore 和 AWI M6 已有本地契约；后续仍需真实 Agent trace |
| B1-Community | community | 已完成：6 个工具由 `CommunitySpace` 承载 | 投诉/活动状态集合、owner/摘要权限、trust pair、同 step 幂等、事件日志和 restore 已有本地契约；后续补状态转移工具和真实 Agent trace |
| B1-Events | events | `create_personal_event`、`rsvp_to_event` | 已有邀请、接受/拒绝、RSVP、出席、评价状态；仍需时间窗口、取消/完成状态和跨 Agent trace |
| B1-Routines | routines | `create_routine`、`run_routine` | 已有 steps、owner、启停、运行计数和执行记录；仍需版本、递归/重复执行边界和真正的 step 编排 |
| B1-Identity | identity | `change_name`、`update_personality_line` | 已有 owner 级身份/人格存储和 restore；仍需历史版本、名字冲突和 replay 断言 |
| B1-External | research / provider | `web_fetch`、`check_weather`、`generate_image` | provider adapter、超时、in_progress → success/fail 状态回写、结果可审计性 |

### P1：工具契约的下一层统一要求

每个写工具完成领域化前，应逐项回答：

- 参数是否有明确类型、枚举、长度和范围？
- 成功是否总有 `status="success"`？失败是否总有 `status="fail"` 或 `error` 和可恢复 `reason`？
- 同一 step 的 Router retry 是否不重复副作用？
- 是否存在 stable id / owner / parent id？
- 是否把关键业务状态写进 replay，而不是只存在 opaque JSON？
- workspace restore 是否恢复 next id、状态机、事件和权限边界？
- Agent 是否只能操作自己的 mailbox、todo、private content 或 owner 资源？
- 是否存在同名工具重复注册或通用实现覆盖专用 owner？
- 外部能力是否明确表示 `in_progress`，而不是返回伪造的外部事实？

### 5.3 本轮 generic 第一轮实现的边界

本轮新增的代码与回归测试覆盖以下可复核路径：

- 导航：地标存在性、坐标映射、目标 Agent 校验、距离与 nearby 查询；
- 记忆/身份：长期记忆、日记按关键词/日期读取、人格线、thought 记录及 restore；
- 事件/routine：事件创建、邀请、接受/拒绝、RSVP、出席、评价，以及 routine 的 owner、steps、运行计数和运行记录；
- 研究/内容：本地 archive 发布、检索、索引，结构化数据上传 checksum，以及拍照 artifact；
- 社交/动作：neural link 请求—共享内存生命周期、能量恢复、自护/idle/动作审计；
- 所有新增状态都进入 `ENV_STATE.json`，恢复后会重建运行时锁并恢复事件嵌套 Agent ID。

这些能力足以支撑 EW 类大场景的基础工具行为，但仍不等于真实地图、外部 Provider 或 LLM 自主选择已经验收。

## 8. 本轮没有做的事情

- 没有启动新的 LLM/模型验证。
- 没有重新跑 5 Agent × 8 小时的 Structured Autonomy。
- 没有覆盖或删除之前的 Contract、deterministic chain、完整 autonomy 和 staged smoke 结果。
- 没有接入真实地图、道路、坐标或外部 provider。
- 没有把 `pid.status=completed` 写成“PIC-001 完整通过”。
- 没有执行 `git add`、`git commit` 或 `git push`。

## 9. 下一步建议

在模型条件恢复前，继续完成以下本地工作即可，不依赖新的 LLM：

1. 以 `afi/world/ew_tools.py` 的 62 个 `generic_contract_tested` 名称为清单，继续将第一轮状态路径升级为逐工具精确签名和领域状态机。
2. 为每一批工具补充参数 Schema、成功/失败 fixture、同 step retry、owner、replay 和 restore 测试。
3. 对 Blog / Governance / Economy / Social 的专用工具继续做跨域状态一致性测试，尤其是 ID、step 和事件顺序。
4. 为官方 validator 增加显式 workspace binding 的项目侧 wrapper 或持续集成测试，避免把 validator 的 lazy registry 限制误判为环境模块失败。
5. 等模型 endpoint 和额度恢复后，再单独启动新的 staged 完整 run；新 run 应与本文件和历史报告并列保存，不覆盖旧证据。

## 10. 可复现命令

以下命令均不调用 LLM：

```bash
cd /path/to/afi-platform
PYTHON_PATH=$(sed -n 's/^PYTHON_PATH=//p' ../.env | head -n 1)
PYTHON_PATH=${PYTHON_PATH:-python3}

"$PYTHON_PATH" -m pytest -q \
  tests/test_tool_contract_audit.py \
  tests/test_ew_tool_catalog.py \
  tests/test_ew_economy_space.py \
  tests/test_planning_space.py \
  tests/test_public_information_crisis.py
```

官方模块 validator 可以继续用于 scanner/tester/router smoke；如果使用它的 registry 检查，应同时运行项目侧的 workspace-bound registry test，不要单独依据 validator 的整体布尔值判断 11 个 custom env 是否可见。

## 11. 相关历史证据

- [113 项 EW 公开工具全量审计矩阵](b1-ew-tool-matrix-113-20260806.md)
- [PIC-001 场景与工具规划](public-information-crisis-scenario-tool-plan.md)
- [PIC-001 Contract Mode 报告](public-information-crisis-pic001-contract-run-report-20260804.md)
- [PIC-001 Structured Autonomy 报告](public-information-crisis-pic001-structured-autonomy-run-report-20260804.md)
- [PIC-001 分析简报](public-information-crisis-pic001-analysis-briefing.md)
- [BlogSpace 实现说明](blog-space-implementation.md)
- [场景 README](../scenarios/public_information_crisis/README.md)
- [113 工具权威目录代码](../afi/world/ew_tools.py)
- [B1 工具目录测试](../tests/test_ew_tool_catalog.py)
