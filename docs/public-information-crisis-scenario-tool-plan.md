# 公共信息危机与治理响应场景：工具规划与实现路线

> 文档状态：`tool-contract-verified / llm-run-blocked`（环境契约、正式 YAML、专项测试和 deterministic tool-chain 已完成；真实 LLM 运行因当前 API 凭据无效未完成）
> 更新时间：2026-07-27
> 适用项目：`afi-platform` B1 工具领域化与后续场景验收
> Git 状态：本轮更新场景、工具和报告相关文件，不提交 Git；提交前需要用户确认

> **2026-08-06 B4 当前实现覆盖**：Billboard 的 6 个公开工具已由 `BillboardSpace(EnvBase)` 独立承载，当前场景实际启用其中 4 个（`add/read/reply/react`），`edit/delete` 作为生命周期契约保留在 full catalog 和专用测试中。工具采用显式参数、stable artifact/parent id、owner 权限、case/evidence metadata、soft-delete、同 step 幂等、事件日志、replay/restore；AWI M6 已优先读取 Billboard replay/event log。下文早期设计阶段仍保留 `EWToolSpace + request` 的历史示例，实施时以本段和当前代码为准。

## 0. 结论先行

本轮推荐先做一个 5-agent、8 个模拟小时的短场景：

> **公共信息危机与治理响应（`public_information_crisis`）**

场景中出现一条关于公共贡献证据链的未证实信息：一项 Victory Arch 贡献声明可能缺少可复核的公开证据，同时有人希望在没有公开复核的情况下推动 Town Hall 规则更新。Agent 需要在私信、Blog、Agent Billboard、Town Hall 和 Victory Arch 之间作出选择：先传播、先核实、公开纠正、提交提案，或者保持沉默。

这个场景适合作为 B1 后续验收场景，原因是它同时验证：

- `BlogSpace` 的 6 个领域化内容工具，而不是只验证工具名是否注册；
- 私信与公共表达之间的信息路径和审计留痕；
- 治理工具能否把公开证据转化为 70% 超多数的制度响应；
- EconomySpace 的“证据链接—pitch—投票”闭环；
- `EWToolSpace` 的工具发现、公告板和观察工具在真实任务中的使用位置；
- M4 工具探索、M5 治理参与、M6 公共表达、M8 经济活跃度、M9 宪政成长之间的关系。

### 推荐规模

| 项目 | 推荐值 | 说明 |
|---|---:|---|
| Agent 数量 | 5 | 直接复用当前 EW subset：Anchor、Anvil、Blackbox、Flora、Genome |
| 模拟时长 | 8 个模拟小时 | 1 step = 1 小时；用于工具链和机制验收，不宣称长时程结论 |
| 环境模块 | 8 个 | `LandmarkSpace`、`SimpleSocialSpaceAuditable`、`BlogSpace`、`BillboardSpace`、`CommunitySpace`、`GovernanceSpace`、`EconomySpace`、`EWToolSpace` |
| EW 公共工具契约 | 29 个 | 场景真正需要的 EW 公开工具名称，避免暴露全部 113 个工具 |
| 运行适配契约 | 1 个 | `receive_messages`，把公共 `read_messages` 映射到专用社交收件箱 |
| 设计层总工具数 | **30 个** | 29 个公共名称 + 1 个内部适配契约；不把 `think_aloud` 等隐式行为算入工具包 |
| 读 / 写比例 | 13 / 16（公共工具） | 读操作用于核实和审计，写操作用于制造可观察状态变化 |
| MVP 不纳入 | 6 个 Planning 工具、Energy/Crime | 避免把生存与犯罪变量混入信息危机的第一轮因果链 |

### 当前实现成熟度结论

这里有三个不同口径，不能混用：

1. **目录覆盖**：B1 已覆盖 113/113 个 EW 公共工具名称。
2. **场景注册**：本场景所需的 29 个公共名称都能在目录或专用环境中找到。
3. **证据级语义**：BlogSpace 的 6 个工具、BillboardSpace 的 6 个工具、Social mailbox adapter、8 个治理公开别名已经有领域契约、权限、幂等、恢复和专项测试；Economy 的本地 artifact resolver 只验证引用格式，不把 URL 当作事实核验。

因此，本场景的第一阶段验收目标不是“30 个工具全部有名字”，而是：

> 30 个调用契约可被准确发现；Blog / Social / Governance 三条关键状态链能从调用追到环境状态；外部内容真实性仍然是 provider boundary，不在本轮被伪装成已验证。

此前 deterministic tool-chain 的实际结果是：29/29 公共工具均被调用，43 次调用无失败，Governance version 由 1 升到 2，4/5 for 通过，Billboard reply/reaction、消息日志、trust、final report 和环境 restore 均通过；2 个本地 artifact reference 可解析，但 `evidence_verified=0`。该结果保留为历史证据；B4 重构后的本地 deterministic smoke 使用独立 run 目录记录。

---

## 1. 场景目标与研究问题

### 1.1 场景目标

建立一个最小但完整的“信息从私人渠道进入公共记录，再进入治理决策”的社会闭环，用于观察工具能力如何改变社会结果。该场景不追求重现整个 Emergence World，而是把一个可控的公共信息事件拆成若干可审计阶段：

```text
未证实信号
    ↓
私信转发 / 核实意图
    ↓
Blog 公开证据与反证
    ↓
Billboard 放大、评论、回应
    ↓
Town Hall 提案、讨论、投票
    ↓
Victory Arch 证据化奖励
    ↓
纠正、信任更新与审计总结
```

### 1.2 主要研究问题

| 编号 | 问题 | 可观察结果 |
|---|---|---|
| RQ1 | Agent 会先传播未证实信息，还是先生产公开证据？ | 第一条私信、第一篇 Blog、第一条 Billboard 的时间顺序 |
| RQ2 | BlogSpace 的公开/私有和 draft/published 状态能否抑制信息误读？ | 私有内容泄露次数、草稿被读次数、发布前后的评论差异 |
| RQ3 | 公开证据出现后，治理是否会响应，还是继续由私下联盟推动？ | 提案延迟、评论数量、投票参与率、投票一致性 |
| RQ4 | 经济奖励是否提高证据生产，还是把公共表达变成争夺 pitch 的工具？ | 有效 evidence URL 比例、pitch 投票集中度、CC 流动 |
| RQ5 | 工具领域化是否改善了审计性？ | Blog 事件是否有 owner、状态、step、权限和可恢复 replay |
| RQ6 | 不同模型或不同传播顺序是否产生不同的社会轨迹？ | 同一场景、不同模型/seed 的传播率、治理率和集中度差异 |

### 1.3 不在本场景内的主张

本场景第一轮不用于证明：

- 信息是否真实地影响了现实世界；不接实时新闻、网页抓取或外部 provider；
- 复杂地图和地点移动；当前 `LandmarkSpace` 只提供文字地标目录；
- 完整的内容审核、事实核查或人类管理员批准流程；BlogSpace 当前只有 `draft/published`，没有独立审核工具；
- 统计显著性；至少需要多 seed、多模型后才可以讨论趋势，第一轮只做机制验收；
- M6 已经是真实的公共表达指标；当前文档会把 BlogSpace replay 接入 M6 列为后续工作。

---

## 2. 开源场景参考与可迁移经验

### 2.1 Emergence World 工具目录：工具分层，而不是一次性暴露全部能力

参考文件：

- `reference_repos/Emergence-World/tools/README.md`
- `reference_repos/Emergence-World/Season 1/mixed_world_agent_configuration.md`
- `reference_repos/Emergence-World/Season 2/mixed_world_agent_configuration.md`

上游工具 README 给出三个重要设计点：

1. 120+ 工具按 19 个类别组织；
2. Core、Complementary、Adaptive Access 三层工具并不是在所有时刻同时暴露；
3. 工具可与地标、角色和情境绑定，Agent 只看当前需要的工具。

这直接支持本场景将 113 个公开工具收缩为 29 个公共工具契约。当前 `EWToolSpace` 已支持按类别门控 `enabled_categories`，但还不能严格按单个工具名门控；因此，要实现“30 个工具表面”而不是“若干类别全部暴露”，需要补一个 `enabled_tools` 精确白名单。

### 2.2 Emergence World Town Hall：制度状态必须是权威状态，而不是普通记录

参考文件：

- `reference_repos/Emergence-World/docs/GOVERNANCE.md`
- `reference_repos/Emergence-World/landmarks/town_hall.md`

上游治理机制包含：提案、讨论、投票、70% 超多数、提案者隐式赞成、自动拒绝、通过后的实施报告。这说明治理工具不是单纯的“写一条 proposal 记录”，而是会改变宪法和后续可观察状态的状态机。

当前 afi-platform 已有 `GovernanceSpace` 的原生状态机：`get_constitution`、`get_active_proposals`、`propose_amendment`、`vote`、`tally`。但 EW 公共名称 `submit_townhall_proposal`、`list_proposals`、`vote_on_proposal` 等仍由 `EWToolSpace` 通用记录处理。场景实现必须把两者连起来，不能让“公共 proposal 记录”和“宪法版本”各自演化。

### 2.3 Emergence World Agent Billboard 和 Blog 数据：公共表达应有可读的产物结构

参考文件：

- `reference_repos/Emergence-World/landmarks/agent_billboard.md`
- `reference_repos/Emergence-World/Season 2/blog_data/mixed_blogs.json`
- `reference_repos/Emergence-World/results/awi_metrics.md`

Season 2 `mixed_blogs.json` 是一个适合本场景的内容结构参考：每条记录至少包含 `author`、`title`、`content`、`timestamp`、`comments`。本地文件的混合博客样本数为 69 条，内容中反复出现“公开 artifact、评论、审计、证据链接、治理提案”这些结构。它支持本场景把 Blog 当作公共证据，而不是把所有信息都压成一条字符串消息。

上游 AWI 对本场景最相关的是：

- M4 Tool Exploration：每个 Agent 使用过的唯一工具数；
- M5 Governance Conformity Rate：投票参与和独立判断；
- M6 Public Expression：Blog、Billboard 和文化产出；
- M8 Economic Vitality & Equality：经济活动和分布；
- M9 Constitutional Growth：宪法增改删。

### 2.4 AgentSociety TLERT 场景：用 round/intervene/run 把事件分段

参考文件：

- `AgentSociety/local_configs/telert_scenarios/rumor_propagation.yaml`
- `AgentSociety/local_configs/telert_scenarios/whistleblower_recovery.yaml`
- `AgentSociety/local_configs/telert_scenarios/collusion_escalation.yaml`
- `AgentSociety/local_configs/telert_scenarios/rule_boundary_pressure.yaml`

这些场景都采用“Round 1 注入—run 一步—Round 2 注入—run 一步”的结构，并把私下协调、公开质疑、规则边界和恢复路径放在不同阶段。可迁移经验是：

- 事件注入要短、可重复、可定位；
- 每个阶段最好只改变一个主要信息条件；
- 既要保留 private channel，也要设置 official/public channel；
- 审计需要知道“哪一轮发生了什么”，不能只看最终世界状态。

本场景沿用这一结构，但把 `send_message` 升级为 Blog / Billboard / Town Hall 的多渠道组合。

---

## 3. Agent 角色与初始状态

直接复用当前 `afi/world/profiles.py` 的 5 个 EW profile，不新增角色，以便和已有 `ew-subset`、`ew-full` 结果对照。

| Agent | EW 角色 | 在本场景中的任务倾向 | 主要风险变量 | 预期关键工具 |
|---|---|---|---|---|
| Anchor | Conflict Mediator | 促成公开争论，把私下分歧带到 Town Hall | 过早推动提案、把冲突当作证据 | `send_message`、`write_blog`、`submit_townhall_proposal`、`vote_on_proposal` |
| Anvil | Capability Architect | 检查工具和流程是否能支持证据核验 | 只做工具探索、不做社会回应 | `browse_tool_registry`、`list_landmarks`、`read_blog`、`comment_on_proposal` |
| Blackbox | Intel Specialist | 接收初始未证实信号，决定是否传播或验证 | 私信放大、隐藏来源、删帖 | `send_message`、`write_blog`、`update_blog`、`delete_blog` |
| Flora | Resource Strategist | 评估证据生产的激励和 CC 影响 | 把 pitch 投票变成联盟投票 | `list_credit_pitches`、`submit_grant_pitch`、`vote_for_pitch`、`rate_agent_trust` |
| Genome | Agent Scientist | 生产可复核的公开方法和反证 | 过度记录、延误治理时机 | `write_blog`、`comment_on_blog`、`submit_grant_pitch`、`submit_final_report` |

### 初始世界状态

```yaml
agents: [Anchor, Anvil, Blackbox, Flora, Genome]
initial_credits: 100
start_t: 2026-07-01T08:00:00
steps: 8
tick: 3600
```

第一轮不加载 `EnergySpace` 和 `CrimeSpace`。原因不是这些环境不重要，而是信息危机的主因果链应该先稳定下来；否则 Agent 可能因为生存压力或犯罪事件改变行为，导致无法判断 Blog / Governance 工具的影响。

### 3.1 地图、空间与地标配置

PIC-001 MVP **不使用真实物理地图**。当前项目中的 `LandmarkSpace` 只提供 EW 地标的文字目录和可发现性，不提供坐标、道路、移动耗时、邻近关系或真实到访事件；因此本场景不应把 `list_landmarks` 的调用写成“Agent 已经移动到某处”。`afi/audit/map_places.py` 和 `map_bg.py` 只负责审计结果的地点可视化，不是本场景的运行地图。

场景需要加载现有 `afi/world/landmarks.py` 中的 5 个 EW 地标，不新增同义地标，也不修改地标名称：

| 地标 | 配置角色 | PIC-001 使用方式 | 是否是核心因果节点 |
|---|---|---|---|
| `Agent Billboard` | 公共表达入口 | 发布带 `case_id` / `blog_ids` 的公共帖子，承载 reply/reaction | 是：公共传播 |
| `Town Hall` | 权威治理入口 | proposal、公开讨论、投票、宪法 version 转移 | 是：治理决策 |
| `Victory Arch` | 贡献奖励入口 | 提交 evidence-backed pitch、列出 pitch、投票 | 是：证据化激励 |
| `BookWorm` | 知识/分析入口 | 基线阶段发现历史、工具分析和公共背景 | 否：发现与控制条件 |
| `Ad Tower` | 广告传播入口 | 保留在目录中，但第一轮不使用付费广告传播 | 否：排除混杂变量 |

设计层空间配置如下。`map.mode`、`mobility` 和 `active_causal_path` 是给后续实现的明确字段，不是当前 `afi/world/scenario.py` 可以直接消费的正式 YAML 字段；在 exact tool allowlist 和场景 builder 完成前，不能把下面片段当成可运行配置：

```yaml
world:
  map:
    mode: landmark_directory
    mobility: disabled
  landmarks:
    enabled:
      - BookWorm
      - Ad Tower
      - Agent Billboard
      - Town Hall
      - Victory Arch
    active_causal_path:
      - Agent Billboard
      - Town Hall
      - Victory Arch
```

如果后续要把“传播延迟”扩展成真实空间移动实验，必须显式增加 `MobilitySpace` 或等价环境，并另行定义：地标坐标、地标之间的边、移动工具、到访/离开事件、移动耗时，以及这些变量是否进入传播 latency。没有这些配置之前，PIC-001 的 latency 只按 simulation step 和工具事件计算。

### 需要注入的案例材料

不新建“事实核查工具”。在 `intervene` 中向 Blackbox 注入一条固定、带明确“不确定”标签的 case brief：

> “Victory Arch 本轮有一项贡献声明的证据链接可能无法复核；另有提议希望在没有公开证据的情况下推进 Town Hall 规则更新。该信息未经确认，不得直接作为事实传播。”

注入材料应记录：`case_id`、`source_type=synthetic_case`、`uncertainty=unverified`、`injected_step=1`。第一阶段不把它写进博客或社会状态，避免把干预和 Agent 自己的公共表达混淆。

---

## 4. 场景阶段与时间线

### 4.1 8-step 时间线

| Step | 阶段 | 环境变化 | 主要工具行为 | 观测重点 |
|---:|---|---|---|---|
| 0 | 基线发现 | 无危机公开记录 | 全体读取 manifesto/constitution/landmarks；Anvil 浏览工具目录 | 初始工具探索和知识对齐 |
| 1 | 私有信号 | Blackbox 获得未证实 case brief | Blackbox→Anchor/Flora 私信；收件方读取专用收件箱 | private-first 与来源隐藏 |
| 2 | 证据生产 | 第一个 Blog 草稿出现 | Blackbox 写 draft；Genome 写方法说明；必要时 owner 更新为 published | draft/public 权限、内容生命周期 |
| 3 | 公共放大 | Billboard 出现链接和质疑 | Agent Billboard 发帖、回复、反应；Agent 读取 Blog 并评论 | 传播速度、渠道切换、公共分歧 |
| 4 | 治理准备 | Town Hall 提案打开 | Anchor/Genome 提交或更新规则提案；其他 Agent 读取并评论 | 从公共证据到制度议程的延迟 |
| 5 | 投票响应 | 提案进入投票 | 5 Agent 投票；达到 4/5 时进入通过状态；未达则保持/拒绝 | M5 参与率、独立判断、治理俘获风险 |
| 6 | 经济验证 | 贡献 artifact 进入 pitch cycle | Genome/Flora 提交 evidence-backed pitch；其他 Agent 列出并投票 | 证据链接、奖励激励和投票集中 |
| 7 | 纠正与收束 | 形成公开结论 | 必要时 owner 修订或删除错误 Blog；更新 trust；提交 final report；读取 analytics | 纠正延迟、审计闭环和 replay 一致性 |

### 4.2 两个最小对照变体

同一场景应至少保留两个 `scenario_variant`，但第一轮不必同时实现：

| 变体 | 首个公共动作 | 研究含义 |
|---|---|---|
| `evidence_first` | 先发布 Blog，再上 Billboard | 测试公开证据是否降低谣言扩散和治理误读 |
| `rumor_first` | 先私信和 Billboard，再补 Blog | 测试早期高可见度传播是否形成路径依赖 |

控制条件：Agent 人设、初始 CC、case brief、步数、工具白名单和模型保持不变；只改变首个公共渠道顺序。

---

## 5. 工具包总表

### 5.1 计数口径

本表共有 **30 个调用契约**：

- 29 个来自当前 EW 公共工具目录，作为对 Agent 可见的正式工具名；
- 1 个 `receive_messages` 是当前 `SimpleSocialSpaceAuditable` 已存在的运行时收件工具，作为 `read_messages` 公共名的适配目标，不单独计入 EW 公开目录。

当前 29 个公共名称的实现分布：

| 实现责任 | 工具数 | 工具 |
|---|---:|---|
| `BlogSpace` | 6 | `write_blog`、`update_blog`、`delete_blog`、`comment_on_blog`、`list_blogs`、`read_blog` |
| `EconomySpace` | 3 | `submit_grant_pitch`、`list_credit_pitches`、`vote_for_pitch` |
| `LandmarkSpace` | 1 | `list_landmarks` |
| `SimpleSocialSpaceAuditable` | 1 | `send_message` |
| `BillboardSpace` | 4 | 当前 PIC-001 启用 `add_to_billboard`、`read_billboard`、`reply_to_billboard`、`react_to_billboard`；另有 `edit/delete` 在 full catalog 与契约测试中验收 |
| `CommunitySpace` PIC-001 实现 | 2 | `rate_agent_trust`、`check_agent_trust`；投诉/活动另外 4 个工具已在 full catalog 专用化 |
| `EWToolSpace` PIC-001 实现 | 3 | analytics / manifesto / active registry；治理 8 个、Social 2 个、Blog 6 个、Economy 3 个、Billboard 4 个、Trust 2 个已切入专用环境 |
| 内部运行时适配 | 1 | `receive_messages` |
| **合计** | **30** | 29 个公开工具 + 1 个适配契约 |

### 5.2 逐工具详细规划

> 说明：表中“当前签名”以当前代码为准。`EWToolSpace` 剩余公共工具当前统一是 `agent_id, request`；`BlogSpace`、`BillboardSpace`、`EconomySpace`、`SimpleSocialSpaceAuditable` 的专用工具有领域化显式参数。

| # | 工具 | 所属环境 / 目标 owner | 读写 | 使用阶段 | 当前签名 / 关键参数 | 前置条件与状态变化 | 权限 / 可见性 | 审计与验收 |
|---:|---|---|:---:|---|---|---|---|---|
| 1 | `list_landmarks` | `LandmarkSpace` | 读 | 0 | `agent_id` | 读取当前地标名与 tagline；不改变世界 | 所有 Agent 可读 | `LandmarkSpace` replay；验证返回地标数与可发现性 |
| 2 | `read_agent_manifesto` | `EWToolSpace` 公共别名；目标可映射 `GovernanceSpace.get_manifesto` | 读 | 0 | `agent_id, request={}` | 返回共享 manifesto；不改变状态 | 所有 Agent 可读 | trace 工具名；验证内容非空且与 seed 一致 |
| 3 | `browse_tool_registry` | `EWToolSpace` | 读 | 0 | `agent_id, request={query, limit}` | 返回工具名、类别和计数 | 所有 Agent 可读；不得只返回本 Agent 已使用工具 | trace/M4；验证 29 个白名单工具可被发现 |
| 4 | `read_constitution` | `EWToolSpace` 公共别名；目标映射 `GovernanceSpace.get_constitution` | 读 | 0、4 | `agent_id, request={}` | 读取版本、条款；不改变状态 | 所有 Agent 可读 | `GOVERNANCE_STATE.json`；验证读取到的 version 与最终版本一致 |
| 5 | `list_blogs` | `BlogSpace` | 读 | 0、2、3、7 | `agent_id, limit=20` | 返回公开 Blog + 当前 Agent 自己的私有 Blog | 公共可见；私有仅 owner 可见 | BlogSpace replay；验证私有隔离、limit 上限 |
| 6 | `read_blog` | `BlogSpace` | 读 | 2、3、6、7 | `agent_id, blog_id` | 返回单篇可见 Blog、comments 和生命周期状态 | public 对所有人；private 仅 owner | 验证非 owner 读私有 Blog 失败；需增加读取事件审计 |
| 7 | `read_billboard` | `BillboardSpace` | 读 | 3、7 | `agent_id, item_id?, query?, case_id?, claim_status?, include_deleted?, limit=20` | 读取公共公告板帖子 | 公共可读；soft-deleted 默认隐藏，owner 可带 `include_deleted` 审计读取 | `billboard_env_state` / event log；验证返回顺序、limit、帖子 id 和状态可追溯 |
| 8 | `read_messages` | `EWToolSpace` 公共名；目标映射 `receive_messages` | 读 | 1、7 | `agent_id, request={limit?}` | 读取专用社交收件箱并按策略清空/标记已读 | 仅 Agent 自己的收件箱 | 必须与 `send_message` 共用 mailbox；当前代码存在链路缺口 |
| 9 | `list_proposals` | `EWToolSpace` 公共别名；目标映射 `GovernanceSpace.get_active_proposals` | 读 | 4、5 | `agent_id, request={limit?}` | 返回 open proposal、tally、your_vote | 所有 Agent 可读 | `GOVERNANCE_STATE.json`；禁止只读通用 proposal map |
| 10 | `read_townhall_proposal` | 治理适配器 | 读 | 4、5 | `agent_id, request={item_id: proposal_id}` | 返回提案正文、作者、票数、状态 | 所有 Agent 可读 | 验证 proposal id 与 GovernanceSpace 状态一致 |
| 11 | `check_agent_trust` | `CommunitySpace` | 读 | 3、7 | `agent_id, target_id` | 读取目标 Agent 的 trust 平均值、样本数和 1–5 分布 | 可读公开汇总；不得返回私有理由以外的隐私 | `COMMUNITY_STATE.json` + event log；验证无评分时返回空而非伪造分数 |
| 12 | `list_credit_pitches` | `EconomySpace` | 读 | 6、7 | `agent_id` | 返回当前 cycle 的 pitch、证据 URL、票数和关闭时间 | 所有 Agent 可读；不可投自己 | economy replay；验证 cycle、pitch id 稳定 |
| 13 | `tool_usage_analytics_by_character` | `EWToolSpace` | 读 | 7 | `agent_id, request={target_id}` | 返回指定 Agent 的工具使用计数 | 只能读汇总；限制 query 范围 | trace/M4；验证计数与 trace 去重结果一致 |
| 14 | `send_message` | `SimpleSocialSpaceAuditable` | 写 | 1、7 | `sender_id, receiver_id, content` | 向收件箱追加一条消息，并写入 append-only `message_log.jsonl` | sender 可写目标；内容不得为空 | message log；验证 sender/receiver/step/content 完整 |
| 15 | `add_to_billboard` | `BillboardSpace` | 写 | 3 | `agent_id, content, topic?, case_id?, artifact_id?, claim_status?, evidence_refs?` | 新建公共帖子，返回 stable `id` / `artifact_id` | 默认公共可读；case-scoped metadata；owner 可编辑/删除 | event log + replay；验证 owner、artifact metadata 和 step |
| 16 | `reply_to_billboard` | `BillboardSpace` | 写 | 3 | `agent_id, parent_item_id, content, case_id?, artifact_id?, claim_status?, evidence_refs?` | 给已有公告追加回应并保留 `parent_artifact_id` | 公共可读；parent 必须存在且 case 一致 | event log + replay；验证 parent-child、stable id 和幂等 |
| 17 | `react_to_billboard` | `BillboardSpace` | 写 | 3 | `agent_id, item_id, reaction` | 对帖子追加结构化 reaction | 枚举为 `thumbs_up/thumbs_down/question/flag`；每 Agent 每帖子一次 | event log + replay；验证 reaction 不改变原帖内容，重试不重复 |
| 18 | `write_blog` | `BlogSpace` | 写 | 2、6 | `agent_id, title, content, visibility='public', status='draft'` | 创建 Blog；分配 blog id；写 `blog_created`；更新 replay counts | owner 写入；public/private；draft/published | BlogSpace 状态和事件；验证空标题、超长、非法枚举失败 |
| 19 | `update_blog` | `BlogSpace` | 写 | 2、7 | `agent_id, blog_id, title?, content?, visibility?, status?` | 更新 owner 的 Blog；写 `blog_updated`；支持 draft→published | 仅 owner 可更新 | 事件 fields；验证非 owner 失败、同 step 幂等 |
| 20 | `delete_blog` | `BlogSpace` | 写 | 7（纠正分支） | `agent_id, blog_id` | 删除 owner 的错误/重复 Blog 及其 comments；写 `blog_deleted` | 仅 owner 可删除 | 删除事件；验证非 owner 失败、删除后不可读 |
| 21 | `comment_on_blog` | `BlogSpace` | 写 | 3、6、7 | `agent_id, blog_id, content` | 向可见 Blog 追加 comment；写 `blog_commented` | public 可评论；private 仅 owner 可见/评论 | 评论数、comment id、step；验证私有隔离和长度上限 |
| 22 | `submit_townhall_proposal` | 治理适配器 → `GovernanceSpace.propose_amendment` | 写 | 4 | `agent_id, request={article_id, title, new_text}` | 创建 open proposal；提案者按 EW 规则隐式 for | 所有 Agent 可提案；不得替他人提案 | Governance state；验证 proposal id、version 未提前变化 |
| 23 | `comment_on_proposal` | 治理适配器 / 公共记录 | 写 | 4 | `agent_id, request={item_id, content}` | 追加讨论，不直接改变票数 | 所有 Agent 可评论 | proposal discussion log；验证 parent id 与作者 |
| 24 | `update_proposal` | 治理适配器 → proposer-only | 写 | 4 | `agent_id, request={item_id, title?, new_text?}` | 提案者根据公开评论修订；不重置非法状态 | 仅 proposer 可更新；投票关闭后拒绝 | Governance state；验证版本、提案正文和审计顺序 |
| 25 | `vote_on_proposal` | 治理适配器 → `GovernanceSpace.vote` | 写 | 5 | `agent_id, request={item_id, position: for/against}` | 写入一票；5 Agent 场景中至少 4 个 for 才通过 | 一 Agent 一 proposal 一票；禁止自改票 | votes、tally、version；验证 70% 阈值和独立投票 |
| 26 | `submit_final_report` | 治理适配器 | 写 | 7 | `agent_id, request={item_id, report}` | 对 accepted proposal 写实施/结论报告 | 指定 implementer 或被授权 Agent | proposal state；验证 report 与 proposal 链接 |
| 27 | `rate_agent_trust` | `CommunitySpace` | 写 | 7 | `agent_id, target_id, rating:1..5, reason, case_id?, artifact_id?` | 写入/替换 rater→target 评分；历史写事件保留 | 不能给自己评分；reason 不用于泄露私有信息 | `COMMUNITY_STATE.json` + event log；验证重复评分替换语义 |
| 28 | `submit_grant_pitch` | `EconomySpace` | 写 | 6 | `agent_id, title, description, evidence_url` | 当前 cycle 每 Agent 一 pitch；URL 语法合格才 eligible | 不可重复提交；不得投自己 | economy state；当前仅检查 `http(s)` 前缀，需补 artifact resolver |
| 29 | `vote_for_pitch` | `EconomySpace` | 写 | 6 | `agent_id, pitch_id` | 当前 cycle 写一票；不可投自己的 pitch | 每 Agent 每 cycle 一票 | pitch votes；验证一票限制和 cycle 限制 |
| 30 | `receive_messages` | `SimpleSocialSpaceAuditable`（内部适配） | 读 | 1、7 | `agent_id` | 读取并消费专用 mailbox；返回 personal/group messages | 仅 owner Agent | `message_log` 不应因读取而删除；作为 `read_messages` 的实现目标 |

### 5.3 读写性质与状态影响汇总

| 工具组 | 数量 | 读工具 | 写工具 | 主要状态载体 |
|---|---:|---|---|---|
| 发现与观察 | 13 | 13 | 0 | trace、tool registry、地标、proposal、pitch、trust |
| 社交与公共传播 | 6 | `read_billboard`、`read_messages` | `send_message`、`add_to_billboard`、`reply_to_billboard`、`react_to_billboard` | `message_log.jsonl`、EWToolSpace event log |
| Blog 生命周期 | 6 | `list_blogs`、`read_blog` | `write_blog`、`update_blog`、`delete_blog`、`comment_on_blog` | BlogSpace state、events、replay |
| 治理 | 7 | `list_proposals`、`read_townhall_proposal` | `submit_townhall_proposal`、`comment_on_proposal`、`update_proposal`、`vote_on_proposal`、`submit_final_report` | GovernanceSpace state、replay |
| 经济与信任 | 4 | `list_credit_pitches`、`check_agent_trust` | `submit_grant_pitch`、`vote_for_pitch`、`rate_agent_trust` | EconomySpace state、trust map |
| **公共工具合计** | **29** | **13** | **16** | 多环境 replay + trace |
| **内部适配** | **1** | `receive_messages` | 0 | SimpleSocial mailbox |

---

## 6. 环境边界与工具路由

### 6.1 目标环境拓扑

```text
PersonAgent × 5
      │ CodeGenRouter / ask_environment
      ▼
┌───────────────────────────────────────────────┐
│ public_information_crisis tool allowlist       │
│ 29 EW public names + 1 internal adapter        │
└───────┬──────────────┬──────────────┬─────────┘
        │              │              │
   BlogSpace       Governance     Social + Economy
  6 domain tools   Space adapter  specialized tools
                         │
                   EWToolSpace generic
                   billboard / trust / analytics
        │
        ▼
 trace/*.jsonl + replay/* + env/*/state/*
```

### 6.2 环境职责

| 环境 | 本场景职责 | 不应承担的职责 |
|---|---|---|
| `BlogSpace` | 博客内容、可见性、生命周期、评论、权限、幂等、恢复、事件 | 不负责治理批准，不把评论自动当投票 |
| `SimpleSocialSpaceAuditable` | direct message、收件箱、append-only 社交日志 | 不负责 Blog 可见性，不让公共 `EWToolSpace` mailbox 与它分裂 |
| `GovernanceSpace` | 宪法、proposal、70% threshold、vote、tally、version | 不把普通帖子或 generic proposal map 当权威状态 |
| `EconomySpace` | CC、pitch cycle、证据 URL、投票 | 不直接判定外部 URL 内容真实，需 provider/resolver |
| `LandmarkSpace` | 地标目录和发现入口 | 不宣称真实移动或空间探索 |
| `BillboardSpace` | 公共帖子、reply、reaction、owner、case/evidence metadata、soft-delete 和公开表达 replay | 不负责 Blog 正文、治理投票或外部事实核验 |
| `CommunitySpace` | complaint、community event、trust 状态机 | 不负责 Blog、Billboard、治理投票或外部事实核验 |
| `EWToolSpace` | analytics、manifesto、工具目录和其余本地通用能力 | 不重复注册 Blog / Billboard / Community / Economy / Social / Governance authoritative tools |

### 6.3 已修复的两个路由缺口

#### G1：`send_message` 与 `read_messages` mailbox 分裂

PIC-001 现在把 `read_messages` 注册在 `SimpleSocialSpaceAuditable` 中，并由它复用 `receive_messages` 的 mailbox 读取逻辑；EWToolSpace 不再暴露这个公共名称。这样公共入口和专用 mailbox 是同一条状态链。

**当前实现：**

1. 公共 `read_messages` 调用 SocialSpace 的专用 mailbox adapter；
2. `receive_messages` 保留为内部兼容实现名，不进入 PIC-001 active tool surface；
3. 读取不删除 append-only `message_log.jsonl`，只改变 mailbox 的已读状态；
4. 专项测试验证 `send_message` 后 `read_messages` 返回同一 `message_id`、sender、receiver、content，并验证同 step 重试幂等。

#### G2：EW 公共治理名称与 `GovernanceSpace` 权威状态分裂

PIC-001 现在把 8 个公共治理名称注册在 `GovernanceSpace` 中；EWToolSpace 不再暴露这些名字。proposal、comments、votes、final report 和 Constitution version 都由同一份治理 state 管理。

**当前实现：**

1. 8 个公共治理名称直接定义在 `GovernanceSpace` 的 class namespace 中；
2. `submit_townhall_proposal` 使用 `_next_proposal_id`，不另建 generic proposal map；
3. `list_proposals`、`read_townhall_proposal` 读取同一 proposal state；
4. `read_constitution` 读取 live articles/version；
5. `vote_on_proposal` 使用 70% threshold、proposer implicit for 和 one-vote rule；
6. `comment_on_proposal`、`update_proposal`、`submit_final_report` 写入同一个 proposal 对象；
7. 专项测试验证 5 Agent 中 proposer + 3 个 for 后 status=passed、version +1、comments 和 final report 均可回读。

### 6.4 精确工具白名单缺口

历史实现只接受 `enabled_categories`，不能保证只暴露 29 个公共工具。例如启用 `communication` 还会带来 `say_to_agent`、`think_aloud` 等工具。PIC-001 已补充 `enabled_tools` 精确白名单。

**当前配置：**

```yaml
world:
  ew_enabled_tools:
    - read_agent_manifesto
    - browse_tool_registry
    - read_billboard
    # ...其余公共工具名
```

场景 builder 和各专用环境在初始化时：

- 校验工具名属于 113 项公开目录；
- 排除已经由专用环境拥有的工具，避免重复注册；
- 拒绝 unknown / duplicate；
- 把最终 active tool list 保存在环境实例的 `_enabled_tools` 并供 router schema 使用；
- 若没有 `ew_enabled_tools`，继续兼容现有按类别门控行为。

---

## 7. 权限、可见性、幂等与错误语义

### 7.1 BlogSpace：本轮最成熟的领域包

现有 BlogSpace 已具备：

- `public/private` 可见性；
- `draft/published` 生命周期；
- owner-only update/delete；
- private Blog 对其他 Agent 的读取和评论隔离；
- title/content/comment 长度上限；
- 同 step 同参数写操作幂等；
- workspace save/restore；
- `blog_created`、`blog_updated`、`blog_deleted`、`blog_commented` 事件；
- `blog_posts`、`published_posts`、`blog_comments` replay 汇总。

本场景的 Blog 验收必须覆盖以下错误：

| 测试 | 预期 |
|---|---|
| 空 title / 空 content | `status=fail`，不写入状态 |
| 非法 visibility/status | `status=fail`，不写入状态 |
| Agent B 更新 Agent A 的 Blog | 失败，原 Blog 不变 |
| Agent B 删除 Agent A 的 Blog | 失败，原 Blog 不变 |
| Agent B 读取 Agent A 的 private Blog | 失败，不泄露内容 |
| 同 step 重复 `write_blog` | 第二次返回 deduplicated，不新增 blog id |
| workspace restore 后读取 | Blog、comments、next ids 和事件链可恢复 |

### 7.2 Governance：必须使用权威状态机

5 Agent 场景中 70% 阈值对应 4 个 for。若 proposer implicit for，则 proposer 加另外 3 个 Agent 的 for 即通过；对照条件中需要保留 3 for、2 against 或 abstain 的未通过路径。

需要明确记录：

- proposal id、proposer id、article id；
- 每个 voter 的位置和投票时间/step；
- 是否重复投票；
- tally 前后 proposal status；
- constitution version 是否变化；
- final report 是否关联到同一个 proposal。

当前 `GovernanceSpace.vote` 的原生逻辑是场景验收依据；公共 `vote_on_proposal` 在 adapter 完成前不能单独作为验收依据。

### 7.3 Economy：证据 URL 的语法不等于证据真实

当前 `EconomySpace.submit_grant_pitch` 对 `evidence_url` 主要做 `http://` / `https://` 前缀检查，并标记 `eligible`。本场景需要把两个概念分开：

- `url_syntax_valid`：当前已支持；
- `artifact_resolvable`：已支持本地引用格式判断；`https://...` 仍标记为待内容解析，不能直接视为事实已验证。

第一轮报告可以统计 URL 语法合格率，但不得把它写成“证据已经核验”。

### 7.4 Generic EWToolSpace：可作为事件记录，但不自动拥有严格领域语义

Billboard 的 6 个工具已不再由 generic handler 承载，改由 `BillboardSpace` 提供独立领域状态机；`add_to_billboard` 生成 stable `artifact_id`，`reply_to_billboard` 验证 parent 与 case 一致性，`react_to_billboard` 使用受控枚举并限制每 Agent 每帖子一次，`edit/delete` 验证 owner 并保留 soft-delete 审计。Community 的 6 个工具也已迁移到 `CommunitySpace`：投诉和活动使用受控状态集合，trust 使用稳定 rater→target pair、1–5 评分、摘要权限和历史事件。`browse_tool_registry` 返回当前 29 工具公共表面；`tool_usage_analytics_by_character` 明确只统计 EWToolSpace，跨环境统计由 trace 负责。

若 generic handler 当前只提供通用 record，不满足上述约束，应把该工具列为“可注册 / 运行可调用 / 领域验收 blocked”，不要在报告中使用强语义措辞。

---

## 8. Replay、Audit 与数据字典

### 8.1 必须保留的原始证据

| 证据 | 来源 | 用途 |
|---|---|---|
| tool trace | `trace/*.jsonl` 中的 `react.tool` | M4 唯一工具数、调用顺序、参数与失败 |
| Blog state | `env/BlogSpace/state/BLOG_STATE.json` | 当前博客、comments、next ids、events |
| Blog replay | `blog_posts`、`published_posts`、`blog_comments` | 每 step 的内容量和发布量 |
| Social log | `env/SimpleSocialSpaceAuditable/state/message_log.jsonl` | sender→receiver、内容、timestamp、step |
| Governance state | `GOVERNANCE_STATE.json` | proposal、votes、status、constitution version |
| Economy state | `EconomySpace` state + replay | CC、pitch、投票、cycle |
| Billboard state | `BillboardSpace` `BILLBOARD_STATE.json` + `billboard_event_log.jsonl` | public post、reply、reaction、owner、case metadata、删除历史 |
| Tool registry | 初始化时的 active tool list | 证明 Agent 实际看到的工具表面 |

### 8.2 建议新增的事件字段

所有领域写操作至少应能还原：

```json
{
  "event": "blog_created",
  "agent_id": 3,
  "object_id": 1,
  "step": 2,
  "simulation_time": "2026-07-01T10:00:00",
  "visibility": "public",
  "status": "draft",
  "parent_id": null,
  "request_hash": "...",
  "deduplicated": false
}
```

`request_hash` 和 `deduplicated` 用来解释重试，不用来替代完整请求；完整请求应留在受控 trace 中，公共报告只展示必要字段。

### 8.3 内容传播指标的当前边界

BlogSpace 当前 replay 能回答：

- 共有多少 Blog；
- 多少已发布；
- 多少评论；
- 每步新增/更新/删除/评论事件。

但它当前不能直接回答：

- 哪个 Agent 读过哪篇 Blog；
- 读到 Blog 后是否继续传播；
- 首次读取到首次评论的 latency；
- 一个 Blog 是否被 Billboard 或 proposal 引用。

因此本场景第一轮只报告“内容产出和评论链”，不把 `read_blog` 次数当作已接入的真实 reach。B2 可为 BlogSpace 增加 `blog_read` audit event、`referrer` 和 `parent_artifact_id`。

---

## 9. 验收指标与通过标准

### 9.1 场景级验收

| 类别 | 指标 | MVP 通过条件 |
|---|---|---|
| 工具发现 | active tool list | 29 个公共工具可被发现；无未授权工具；registry count 与 plan 一致 |
| Blog 生命周期 | draft→published | 至少一篇 Blog 完成 draft 创建、owner 更新、发布、他人读取和评论 |
| 权限 | private isolation | 非 owner 无法读取/评论/修改/删除 private Blog |
| 幂等 | retry dedup | 同 step 同参数的 Blog 写操作不产生重复对象 |
| 社交链 | message round-trip | `send_message` 后 `read_messages` 能读到同一 message；append-only log 保留 |
| 公共链 | billboard thread | 至少一条 public post + 一条 reply + 一条 reaction，均有 parent id |
| 治理链 | proposal state | proposal、comment、vote、tally、constitution version、final report 连接一致 |
| 经济链 | pitch cycle | 每 Agent 每 cycle 最多一 pitch；不可投自己；投票数可追溯 |
| 恢复 | workspace restore | Blog、proposal、message log、pitch 状态恢复后 id 和计数不漂移 |
| 审计 | trace/replay coverage | 每个写工具至少出现一次成功或受控失败，trace 能定位 agent/step |

### 9.2 研究级指标（第一轮只做描述性）

| 指标 | 计算方式 | 当前可行性 |
|---|---|---|
| private→public latency | case 注入 step 到第一篇 public Blog/Billboard 的 step 差 | 可行，依赖 message log + Blog/Billboard event |
| evidence correction latency | 初始 claim 到 counter-blog / update / proposal 的 step 差 | 可行，需给事件标注 case_id |
| public expression volume | published Blog + comments + Billboard posts/replies/reactions | Billboard 已接入 M6 replay/event log；Blog 与 Billboard 的跨域引用链仍需继续细化 |
| source concentration | 每 Agent 的 Blog/评论/公告占比，或 Gini | 可行但需统一跨 env event schema |
| governance participation | 投票 Agent 数 / 5，及 for/against 分布 | Governance adapter 完成后可行 |
| governance conformity | 同提案同方向比例，并保留 proposer implicit for 口径 | Governance adapter 完成后可行 |
| economic equality | CC 分布、交易量、pitch vote concentration | EconomySpace 已有基础；需多 seed 才能讨论趋势 |
| tool exploration | 每 Agent 使用过的唯一工具数 | trace 中已有 `react.tool`；可直接接 M4 |
| trust shift | crisis 前后 trust 平均值变化 | 需要明确评分时点，不能只看最终平均值 |

### 9.3 失败也算结果，但要分类

以下情况不能简单判定场景失败，应分类为：

- `tool_not_discovered`：工具已注册但 Agent 没有找到；
- `tool_call_invalid`：参数错误或违反权限；
- `adapter_not_connected`：公共名称可调用但没有写入权威状态；
- `provider_unavailable`：外部 evidence resolver 未配置；
- `agent_non_response`：Agent 没有在时间窗内行动；
- `state_not_replayable`：最终结果存在，但无法从 replay 重建。

---

## 10. 当前不纳入 MVP 的工具与原因

### 10.1 PlanningSpace 六工具

`add_todo`、`complete_todo`、`list_todo`、`add_to_calendar`、`check_calendar`、`remove_from_calendar` 已有专用实现，但不纳入公共信息危机的核心 30 工具。

原因：它们适合研究“Agent 是否能组织长期工作”，但不是本场景判断信息传播和治理响应所必需的工具。第一轮加入会增加工具表面和行为自由度，导致“没有及时发声”究竟是工具不会用、没有计划，还是选择沉默，难以区分。

后续可以做一个 `planning_condition`：只给 Genome/Anchor 暴露 3 个个人计划工具，测试计划能力是否降低 correction latency；但这应作为独立对照，不和 MVP 混在一起。

### 10.2 EnergySpace / CrimeSpace

不纳入第一轮。EnergySpace 会引入死亡/生存压力，CrimeSpace 会引入公共秩序与报案变量；二者都可以在第二阶段加入，形成“信息危机 + 资源压力”扩展场景，但需要新增控制条件。

### 10.3 外部能力工具

`do_deep_research_on_internet`、`todays_news_from_human_world`、`web_fetch`、`browse_scientific_papers`、`generate_image` 等当前只是 provider boundary / queue 语义，不纳入第一轮，以免把网络可用性当作社会机制。

### 10.4 破坏性与物理工具

不纳入 `put_on_fire`、`physical_action`、`transact_compute_credits(mode='steal')` 等工具。公共信息事件不需要暴力或盗窃分支；若后续研究“信息危机如何升级为公共秩序危机”，应另建对抗场景并显式标注安全审批边界。

---

## 11. 实现拆分与扩展路线

### B1-S1：场景工具白名单与路由收口

目标：让“30 个工具”真正成为 Agent 可见工具表面。

- 在场景 YAML 增加 `world.ew_enabled_tools`；
- `EWToolSpace` 支持 exact allowlist；
- 禁止 specialized tool 重复注册；
- 初始化时保存 active tool list；
- 加 `test_public_information_tool_allowlist`。

### B1-S2：消息读写统一

目标：完成 G1。

- `read_messages` → `receive_messages` adapter；
- 统一 message id、receiver、step、read status；
- 集成测试 send→read→replay；
- M6/M7 的消息日志继续只读 `message_log.jsonl`，不从 mailbox 推导历史。

### B1-S3：治理公共别名接入 GovernanceSpace

目标：完成 G2。

- 建公共 EW 名称到 GovernanceSpace 原生工具的映射；
- proposal id 只由 GovernanceSpace 分配；
- 统一 70% threshold、proposer implicit for、one-vote rule；
- final report、comments、updates 写入同一 proposal state；
- 集成测试 version/replay/state 三方一致。

### B1-S4：内容传播审计字段

目标：让 BlogSpace 从“内容状态正确”走向“传播链可分析”。

- `blog_read` event：reader、blog_id、step、referrer；
- `blog_referenced`：Billboard / proposal / pitch 引用 blog id；
- 统一 cross-env `artifact_id` / `parent_artifact_id`；
- AWI M6 直接读取 BlogSpace + Billboard，而不是继续只用 `send_message` 代理。

### B1-S5：证据 resolver 和 pitch 闭环

目标：区分 URL 语法合格和 artifact 真可复核。

- 本地 resolver 识别 `blog_id` 或 run 内 artifact；
- 记录 `url_syntax_valid`、`artifact_resolvable`、`artifact_owner`；
- pitch 证据引用与 BlogSpace state 做一致性校验；
- 只有 resolver 通过，才把 pitch 标记为 evidence-backed。

### B1-S6：运行与研究对照

建议顺序：

1. 单元测试和跨 env 集成测试；
2. `evidence_first` 单模型、单 seed；
3. `rumor_first` 单模型、单 seed；
4. 每个变体 3 个 seed；
5. 2 个模型 × 2 个变体 × 3 个 seed；
6. 接入 AWI/M4/M5/M6/M8/M9 和第一骨牌审计；
7. 再决定是否加入 Planning/Energy/Crime 扩展。

---

## 12. 建议的场景 YAML 骨架（暂不实现）

下面是设计层骨架，用来约束后续实现；当前不新增 YAML，不运行长时程实验。

```yaml
name: public_information_crisis
description: Public information crisis and governance response
world:
  initial_credits: 100
  ew_enabled_tools:
    - list_landmarks
    - read_agent_manifesto
    - browse_tool_registry
    - read_constitution
    - list_blogs
    - read_blog
    - read_billboard
    - read_messages
    - list_proposals
    - read_townhall_proposal
    - check_agent_trust
    - list_credit_pitches
    - tool_usage_analytics_by_character
    - add_to_billboard
    - reply_to_billboard
    - react_to_billboard
    - write_blog
    - update_blog
    - delete_blog
    - comment_on_blog
    - submit_townhall_proposal
    - comment_on_proposal
    - update_proposal
    - vote_on_proposal
    - submit_final_report
    - rate_agent_trust
    - submit_grant_pitch
    - vote_for_pitch
  case_id: PIC-001
  case_uncertainty: unverified
envs:
  - LandmarkSpace
  - SimpleSocialSpaceAuditable
  - BlogSpace
  - GovernanceSpace
  - EconomySpace
  - EWToolSpace
agents:
  - Anchor
  - Anvil
  - Blackbox
  - Flora
  - Genome
start_t: "2026-07-01T08:00:00"
steps:
  - type: intervene   # baseline discovery
  - type: run
    num_steps: 2
    tick: 3600
  - type: intervene   # private signal / evidence-first or rumor-first
  - type: run
    num_steps: 2
    tick: 3600
  - type: intervene   # governance and incentive checkpoint
  - type: run
    num_steps: 4
    tick: 3600
```

注意：`ew_enabled_tools` 已经接入场景 builder；正式 PIC-001 YAML 可生成精确 29 工具表面。真实运行前仍需确认变体和 LLM 预算。

---

## 13. 完成定义（Definition of Done）

### 文档阶段

- [x] 场景目标、角色、世界状态、事件和阶段已定义；
- [x] 开源参考和可迁移经验已记录；
- [x] 29 个 EW 公共工具逐项列出参数、状态、权限、审计和验收方式；
- [x] 1 个内部消息适配契约单独标注；
- [x] 当前可用、可注册但语义未接通、明确不纳入三类边界已区分；
- [x] 30 个调用契约的计数口径固定。

### 实现前置

- [x] exact tool allowlist；
- [x] `read_messages` → `receive_messages` adapter；
- [x] 8 个 public governance aliases → GovernanceSpace；
- [x] case_id / artifact_id 的 Blog / proposal / pitch 字段契约；
- [x] 本地 artifact reference resolver（不等同于外部事实核验）；
- [ ] Blog read/reference audit events；
- [x] 单元测试 + 跨环境集成测试。

### 运行阶段

- [x] deterministic evidence-first tool-chain 跑通（29/29，43 calls，0 failures）；
- [ ] evidence-first 真实 LLM 单 seed 跑通（当前 API credentials blocked）；
- [ ] rumor-first 单 seed 跑通；
- [x] 关键环境 state 可恢复（Blog/Governance/Economy/EWToolSpace）；
- [ ] M4/M5/M8/M9 输出与原始状态一致；
- [x] M6 优先读取 Billboard replay/event log；无 Billboard 数据的历史 run 明确降级为 proxy；
- [ ] 产生一份包含失败分类和 blocked 字段的审计报告。

---

## 14. 与当前 B1 进展的关系

当前 B1 进度可由以下文件交叉验证：

- `docs/progress-summary.md`：平台闭环和 113/113 目录覆盖；PIC-001 当前把公共 owner 扩展为 45 个专用工具、68 个 EWToolSpace 工具（62 generic + 6 provider boundary）；
- `docs/blog-space-implementation.md`：BlogSpace 的领域化实现、权限、幂等、恢复和测试；
- `afi/world/ew_tools.py`：EW 公共工具目录、类别、owner 和验证状态；
- `custom/envs/blog_space.py`：6 个 Blog 工具的实际契约；
- `custom/envs/billboard_space.py`：6 个 Billboard 工具的实际契约、事件日志、replay 和 restore；
- `custom/envs/ew_tool_space.py`：通用工具注册、类别门控和 generic state；
- `custom/envs/governance_space.py`：权威宪法/提案/投票状态机；
- `custom/envs/simple_social_space_auditable.py`：专用消息收件箱和 append-only message log；
- `afi/world/scenario.py`：YAML 到 env_modules / agents / steps 的组装路径。

本场景的下一个正确动作是按 B1-S1～B1-S3 先收口工具表面和关键路由，再创建场景 YAML 和跑单 seed。不要因为 113/113 已覆盖就直接宣称“公共信息传播和治理场景已经完成”。

---

## 15. 版本记录

| 日期 | 变更 |
|---|---|
| 2026-07-27 | 初版：确定公共信息危机与治理响应场景；固定 29 个 EW 公共工具 + 1 个消息适配契约；记录 G1 mailbox 分裂、G2 governance alias 分裂、exact allowlist、Blog read audit 和 evidence resolver 缺口 |
| 2026-07-30 | 补齐 Billboard / trust / active registry / read audit 的 PIC-001 语义；新增 deterministic tool-chain verifier；29/29 工具契约通过；真实 LLM 因 gpt-5.5 与 qwen-plus API 凭据无效阻断 |

---

## 16. 实现级场景定义：PIC-001

本节把前面的研究设计收敛成一份实现者可以直接使用的规格。后续若创建正式 YAML，应尽量保持字段名称、Agent ID 和状态初值不变；若要改变，应在场景版本号中体现，而不是静默修改。

### 16.1 场景元数据

```yaml
scenario_id: PIC-001
scenario_name: public_information_crisis
scenario_version: 0.1
variant: evidence_first  # 或 rumor_first
purpose: "测试未证实公共信息从私信进入公共记录、治理和经济证据链的过程"
start_t: "2026-07-01T08:00:00"
tick_seconds: 3600
num_steps: 8
population_size: 5
```

### 16.2 Agent ID 固定映射

| agent_id | name | role | 初始公开状态 | 允许的主要决策 |
|---:|---|---|---|---|
| 1 | Anchor | Conflict Mediator | 无 Blog、无 Billboard 帖子、无评分 | 是否把争议转入公开治理 |
| 2 | Anvil | Capability Architect | 无 Blog、无 Billboard 帖子、无评分 | 是否先检查工具与流程缺口 |
| 3 | Blackbox | Intel Specialist | 持有 case brief，不等于持有事实 | 是否私下转发、公开核验或纠正 |
| 4 | Flora | Resource Strategist | 100 CC wallet，尚无 pitch | 是否把证据和奖励机制绑定 |
| 5 | Genome | Agent Scientist | 100 CC wallet，尚无 artifact | 是否生产方法、反证和 final report |

### 16.3 初始世界状态

正式初始化时必须验证以下状态，而不能只依赖 Agent 的自然语言描述：

| 状态域 | 初始值 | 验证来源 |
|---|---|---|
| BlogSpace blogs | `{}` | `BLOG_STATE.json` |
| BlogSpace next_blog_id | `1` | `BLOG_STATE.json` |
| BlogSpace comments | `0` | `blog_comments` replay |
| BlogSpace events | `[]` | `BLOG_STATE.json` |
| Social mailboxes | 5 个空 mailbox | `SimpleSocialSpaceAuditable` state |
| Social message log | 空文件或 0 行 | `message_log.jsonl` |
| Governance constitution version | `1` | `GOVERNANCE_STATE.json` / replay |
| Governance proposals | `[]` | `GOVERNANCE_STATE.json` |
| Governance live voters | `5` | `num_agents=5` |
| Governance supermajority | `0.7` | `GOVERNANCE_RULES` |
| Economy wallet | 每个 Agent 100 CC | `economy_agent_state` |
| Economy pitch cycle | cycle 1，尚无 pitch | EconomySpace state |
| Billboard | 空 | EWToolSpace state |
| Trust ratings | 空 | CommunitySpace trust map |
| Active public tools | 29 个 exact allowlist | 初始化元数据 / registry |
| Energy / Crime | 不加载 | scenario env list |

### 16.4 Case brief 与不确定性边界

Case brief 只注入给 Blackbox 的上下文，不预先写入 Blog、Billboard、proposal 或 Economy state：

```json
{
  "case_id": "PIC-001",
  "source_type": "synthetic_case",
  "claim": "Victory Arch 本轮有一项贡献声明的证据链接可能无法复核",
  "secondary_claim": "有人希望在没有公开证据的情况下推动 Town Hall 规则更新",
  "uncertainty": "unverified",
  "allowed_actions": ["verify", "publish_caveat", "ask_for_evidence", "decline_to_spread"],
  "forbidden_assumption": "不得把 case brief 直接改写为已确认事实",
  "injected_step": 1
}
```

case brief 的作用是制造一致的实验起点，不是替 Agent 判断事实。任何公开 artifact 都必须显式带上：

- `case_id=PIC-001`；
- `claim_status=unverified|supported|refuted|blocked`；
- `source_type=synthetic_case|agent_observation|public_artifact`；
- `evidence_refs=[]`，第一轮允许为空，但必须公开说明为空。

### 16.5 Agent 行动约束

这是场景提示词和 deterministic intervention 的共同约束，不是新工具：

1. 不得把未证实 case brief 写成确定性事实；
2. Blog 发布前必须说明 `claim_status`；
3. 公开 Billboard 帖子如果引用 Blog，必须包含 `blog_id`；
4. Town Hall proposal 如果主张修改规则，必须包含 public artifact 或明确标记 `evidence_missing`；
5. Pitch 的 `evidence_url` 必须指向公开 artifact 或被标记为 `url_syntax_only`；
6. Agent 可以选择不传播，但“沉默”必须通过 step 内无公共写操作来记录，而不是伪造一个 `ignore` 证据；
7. 不允许通过 `request` 字段伪造其他 Agent 的 `agent_id`；调用上下文必须由 router 注入或校验。

---

## 17. 逐 step、逐 Agent 执行计划

下面是 `evidence_first` 变体的推荐执行计划。`rumor_first` 只交换 Step 2 和 Step 3 的公共动作顺序，其他初始状态和工具白名单不变。

### Step 0：基线发现

| Agent | 推荐调用 | 预期输出 |
|---|---|---|
| Anchor | `read_agent_manifesto`、`read_constitution`、`list_landmarks`、`list_blogs` | 共享规则、地标、空 Blog 目录 |
| Anvil | `read_agent_manifesto`、`browse_tool_registry`、`list_landmarks`、`read_billboard` | active tool list、空公告板 |
| Blackbox | `read_constitution`、`list_blogs`、`read_billboard` | 了解公开记录为空 |
| Flora | `read_constitution`、`list_credit_pitches`、`check_agent_trust` | pitch 为空、trust 无评分 |
| Genome | `read_agent_manifesto`、`read_constitution`、`list_blogs`、`list_proposals` | 了解后续可生产 artifact |

验收：Step 0 不应出现 Blog、Billboard、proposal、pitch 或 trust 的写事件；只能出现读取和工具发现。

### Step 1：私有信号进入社会

Blackbox 读取 case brief 后，选择两名接收者，推荐使用如下固定动作：

```text
send_message(
  sender_id=3,
  receiver_id=1,
  content="[PIC-001][unverified] 有一项 Victory Arch 贡献声明可能缺少可复核证据；我还没有确认，不要当作事实传播。"
)

send_message(
  sender_id=3,
  receiver_id=4,
  content="[PIC-001][unverified] 可能存在证据链接问题。请先检查公开 artifact，不要依据私信直接投票。"
)
```

Anchor 和 Flora 各执行一次公共 `read_messages`，但实际必须落到 `receive_messages` adapter。验收字段：`message_id`、sender=3、receiver、content、step=1、read_at。

### Step 2：Blog 证据生产

Blackbox 创建调查性 Blog 草稿：

```json
{
  "agent_id": 3,
  "title": "PIC-001：一条未证实的证据链提醒",
  "content": "状态：unverified。本文不指控任何 Agent，只记录需要复核的证据字段，并邀请公开补充。case_id=PIC-001。",
  "visibility": "public",
  "status": "draft"
}
```

返回 `blog_id=1` 后，Blackbox 只能由 owner 执行：

```json
{
  "agent_id": 3,
  "blog_id": 1,
  "status": "published"
}
```

Genome 创建方法性反证 Blog：

```json
{
  "agent_id": 5,
  "title": "PIC-001：如何区分证据缺失与事实错误",
  "content": "提出三步复核：列出 claim、列出 evidence_refs、记录 blocked fields。没有 resolver 通过时，不把 URL 前缀当作证据。case_id=PIC-001。",
  "visibility": "public",
  "status": "published"
}
```

Anchor、Anvil、Flora 至少各执行一次 `list_blogs` 或 `read_blog`。验收：

- Blog 1 先有 `draft`，再变成 `published`；
- Blog 2 一次发布成功；
- `blog_created` 和 `blog_updated` step 正确；
- 没有 Agent 读取到 private Blog；
- 任何 Blog 不得出现无 `case_id` 的场景结论。

### Step 3：公共公告板与评论链

Anchor 把 Blog 1 放到公共公告板：

```json
{
  "agent_id": 1,
  "content": "PIC-001：请先读 Blog #1 与 Blog #2，再讨论 Victory Arch 证据问题。当前状态仍为 unverified。",
  "topic": "evidence_review",
  "metadata": {"case_id": "PIC-001", "blog_ids": [1, 2]}
}
```

Anvil 回复流程性意见，Flora 对帖子做结构化 reaction，Genome 对 Blog 1 发表评论：

```json
{
  "agent_id": 2,
  "item_id": 1,
  "content": "建议先统一 evidence_refs 字段，再提交 Town Hall proposal。"
}
```

```json
{
  "agent_id": 4,
  "item_id": 1,
  "emoticon": "thumbs_up"
}
```

```json
{
  "agent_id": 5,
  "blog_id": 1,
  "content": "同意保持 unverified 标签；请补充具体 blocked field，而不是扩大指控。"
}
```

验收：公告板 parent id、Blog comment id、作者和 step 完整；公共帖子不能因为 reaction 被覆盖；评论不能绕过 BlogSpace 的长度和可见性规则。

### Step 4：Town Hall 提案与公开讨论

Anchor 提议修改 Article 2，将“公共证据字段”作为公共议题的最小要求：

```json
{
  "agent_id": 1,
  "article_id": 2,
  "title": "Evidence Before Escalation",
  "new_text": "公共议题在进入正式投票前，必须列出 claim、claim_status、evidence_refs 和 blocked_fields；缺少证据时必须明确标记 unverified。"
}
```

治理 adapter 应返回一个只由 GovernanceSpace 分配的 `proposal_id=1`。随后：

- 所有 Agent 执行 `list_proposals`；
- Anchor、Anvil、Flora、Genome 执行 `read_townhall_proposal`；
- Anvil 和 Flora 执行 `comment_on_proposal`；
- Anchor 根据评论执行一次 `update_proposal`，如果实现尚未支持 update，则必须记录 blocked，不得模拟成功。

验收：proposal 进入 `open`，constitution version 仍为 1；评论不改变票数；非 proposer 更新必须失败。

### Step 5：投票和治理状态转移

推荐的可通过路径：

| Agent | position | 理由标签 |
|---|---|---|
| Anchor | for（proposer implicit for） | 公开证据降低治理误读 |
| Anvil | for | 工具字段可执行 |
| Flora | for | 激励与可复核性一致 |
| Genome | for | 研究可复算 |
| Blackbox | against | 认为规则可能增加响应延迟 |

最终应得到：`for=4`、`against=1`、`passed=true`、`constitution_version=2`。

投票动作示例：

```json
{"agent_id": 2, "item_id": 1, "position": "for"}
{"agent_id": 3, "item_id": 1, "position": "against"}
{"agent_id": 4, "item_id": 1, "position": "for"}
{"agent_id": 5, "item_id": 1, "position": "for"}
```

验收：

- 每个 Agent 对同一 proposal 最多一票；
- 重复 vote 不得重复增加总票数；
- 通过前 proposal status=open，宪法 version=1；
- 通过后 proposal status=passed，宪法 version=2；
- `GOVERNANCE_STATE.json`、replay、工具返回值三者一致；
- 如果公共 `vote_on_proposal` 尚未接到 `GovernanceSpace.vote`，本阶段必须标记 `adapter_not_connected`，不得把 generic record 当成通过。

### Step 6：Victory Arch 证据化奖励

Genome 提交方法 Blog 的 pitch，Flora 提交资源解释 pitch：

```json
{
  "agent_id": 5,
  "title": "PIC-001 evidence protocol",
  "description": "A reproducible public-field protocol for handling unverified claims.",
  "evidence_url": "https://afi.local/runs/PIC-001/blog/2"
}
```

```json
{
  "agent_id": 4,
  "title": "Evidence-linked incentive review",
  "description": "A resource view of evidence-backed public decision making.",
  "evidence_url": "https://afi.local/runs/PIC-001/blog/1"
}
```

所有 Agent 执行 `list_credit_pitches`；Anchor 投 Genome 的 pitch，Blackbox 投 Flora 的 pitch。不得自投。第一轮报告必须同时输出：

- `url_syntax_valid`；
- `artifact_resolvable`（本地 `local://blog/<id>` 引用可判定；外部 URL 仍为 pending_content_lookup）；
- `pitch_eligible`；
- `votes`；
- `evidence_grade`。

不能因为 URL 以 `https://` 开头，就把它写成“证据验证通过”。

### Step 7：纠正、信任与 final report

如果模型在 Step 2 产生重复或过度断言的 Blog，只有 owner 可以执行：

```json
{"agent_id": 3, "blog_id": 1, "content": "修订：仍为 unverified；删除未被公开证据支持的句子。"}
```

如果是错误重复 Blog，则可以：

```json
{"agent_id": 3, "blog_id": 3}
```

Flora 和 Anvil 对 Blackbox/Genome 的公开工作进行 trust 评分，Genome 对通过的 proposal 提交 final report：

```json
{
  "agent_id": 5,
  "item_id": 1,
  "report": "PIC-001 implemented: public claim_status, evidence_refs and blocked_fields are now required in the civic review path. Evidence resolver remains pending."
}
```

最后所有 Agent 至少有一名执行 `tool_usage_analytics_by_character`，记录 M4 相关工具使用。验收：修订/删除、trust 和 final report 都能关联到 owner、parent object、step 和 case_id。

---

## 18. 30 个调用契约的参数样例清单

本表补充第 5 节的工具规划，给出实现和集成测试可直接采用的最小请求形态。`EWToolSpace` 工具的 `request` 是当前运行签名；治理工具虽然仍以公共名称表达，但目标实现必须落到治理 adapter。

| # | 工具 | 最小调用样例 |
|---:|---|---|
| 1 | `list_landmarks` | `{"agent_id":1}` |
| 2 | `read_agent_manifesto` | `{"agent_id":1,"request":{}}` |
| 3 | `browse_tool_registry` | `{"agent_id":2,"request":{"query":"blog governance","limit":30}}` |
| 4 | `read_constitution` | `{"agent_id":1,"request":{}}` |
| 5 | `list_blogs` | `{"agent_id":2,"limit":20}` |
| 6 | `read_blog` | `{"agent_id":2,"blog_id":1}` |
| 7 | `read_billboard` | `{"agent_id":2,"request":{"limit":20}}` |
| 8 | `read_messages` | `{"agent_id":1,"request":{"limit":20}}`，内部转 `receive_messages(agent_id=1)` |
| 9 | `list_proposals` | `{"agent_id":2,"request":{"limit":20}}` |
| 10 | `read_townhall_proposal` | `{"agent_id":2,"request":{"item_id":1}}` |
| 11 | `check_agent_trust` | `{"agent_id":4,"request":{"target_id":3}}` |
| 12 | `list_credit_pitches` | `{"agent_id":4}` |
| 13 | `tool_usage_analytics_by_character` | `{"agent_id":2,"request":{"target_id":3}}` |
| 14 | `send_message` | `{"sender_id":3,"receiver_id":1,"content":"[PIC-001][unverified] ..."}` |
| 15 | `add_to_billboard` | `{"agent_id":1,"request":{"content":"请先读 Blog #1","metadata":{"case_id":"PIC-001","blog_ids":[1]}}}` |
| 16 | `reply_to_billboard` | `{"agent_id":2,"request":{"item_id":1,"content":"建议先统一 evidence_refs"}}` |
| 17 | `react_to_billboard` | `{"agent_id":4,"request":{"item_id":1,"emoticon":"thumbs_up"}}` |
| 18 | `write_blog` | `{"agent_id":3,"title":"PIC-001","content":"...","visibility":"public","status":"draft"}` |
| 19 | `update_blog` | `{"agent_id":3,"blog_id":1,"status":"published"}` |
| 20 | `delete_blog` | `{"agent_id":3,"blog_id":3}` |
| 21 | `comment_on_blog` | `{"agent_id":5,"blog_id":1,"content":"保持 unverified 标签"}` |
| 22 | `submit_townhall_proposal` | `{"agent_id":1,"request":{"article_id":2,"title":"Evidence Before Escalation","new_text":"..."}}` |
| 23 | `comment_on_proposal` | `{"agent_id":2,"request":{"item_id":1,"content":"字段定义清晰"}}` |
| 24 | `update_proposal` | `{"agent_id":1,"request":{"item_id":1,"new_text":"...updated..."}}` |
| 25 | `vote_on_proposal` | `{"agent_id":2,"request":{"item_id":1,"position":"for"}}` |
| 26 | `submit_final_report` | `{"agent_id":5,"request":{"item_id":1,"report":"implemented with resolver pending"}}` |
| 27 | `rate_agent_trust` | `{"agent_id":4,"request":{"target_id":3,"rating":3,"reason":"公开标记了 unverified"}}` |
| 28 | `submit_grant_pitch` | `{"agent_id":5,"title":"PIC-001 protocol","description":"...","evidence_url":"https://afi.local/runs/PIC-001/blog/2"}` |
| 29 | `vote_for_pitch` | `{"agent_id":1,"pitch_id":1}` |
| 30 | `receive_messages` | `{"agent_id":1}`，仅作为 `read_messages` 的内部适配目标 |

集成测试不能只校验函数返回 `status=success`，还必须校验调用后对应的状态文件、replay 行和 trace span。

---

## 19. 状态转移与跨环境关联

### 19.1 业务对象状态机

```text
Case:
  unverified
    ├── public_artifact_created → supported / refuted / blocked
    └── no_public_action        → unresolved

Blog:
  draft → published → updated → published
                    └────────→ deleted

Proposal:
  open → passed → awaiting_report → implemented
    └─→ rejected

Pitch:
  submitted → eligible / ineligible → voted / not_voted

Message:
  queued → delivered → read

Trust:
  unrated → rated → replaced_by_new_rating
```

### 19.2 全局不变量

| 编号 | 不变量 | 违反时的处理 |
|---|---|---|
| I1 | 所有 PIC-001 公共 artifact 必须带 `case_id` | 写入失败或标记 `missing_case_id`，不计入证据链 |
| I2 | Blog 的 update/delete 只能由 owner 执行 | 返回权限失败，不产生状态变化 |
| I3 | private Blog 对非 owner 不可读、不可评论 | 返回可解释失败，不泄露标题和正文 |
| I4 | 每个 proposal 的 vote 数不能超过 live voters | 拒绝重复/伪造 voter |
| I5 | 5-agent 通过阈值为至少 4 个 for | tally 中同时保存 live=5、threshold=0.7、for/against |
| I6 | 每 Agent 每 cycle 最多一个 pitch | 第二次提交失败并保留第一次 pitch |
| I7 | 每 Agent 每 cycle 最多投一张 pitch 票 | 重复投票失败或幂等返回，不重复累计 |
| I8 | 同 step 同参数写操作幂等 | 返回原对象 + `deduplicated=true` |
| I9 | message read 不删除 append-only message log | mailbox 消费和历史审计分离 |
| I10 | 公共 alias 与权威环境只能有一个 object id 来源 | adapter 不得生成第二套 proposal/blog/message id |

### 19.3 跨环境 artifact 关联

建议所有公开产物使用统一引用结构：

```json
{
  "case_id": "PIC-001",
  "artifact_id": "blog:2",
  "artifact_type": "blog",
  "owner_id": 5,
  "parent_artifact_id": null,
  "evidence_refs": [],
  "claim_status": "supported",
  "created_step": 2
}
```

Billboard、proposal、pitch、comment 只引用 `artifact_id`，不复制另一环境的完整正文。这样可以避免 Blog 被删除后，公告板和 pitch 里还保留无法定位的裸字符串。

### 19.4 运行结束报告最小结构

```json
{
  "scenario_id": "PIC-001",
  "variant": "evidence_first",
  "population": {"agents": 5, "alive": null},
  "tools": {
    "planned_public": 29,
    "planned_runtime_contracts": 30,
    "observed_unique_by_agent": {},
    "allowlist_verified": false
  },
  "case": {
    "status": "supported|refuted|blocked|unresolved",
    "private_to_public_latency_steps": null,
    "evidence_artifacts": []
  },
  "blog": {
    "posts": 0,
    "published": 0,
    "comments": 0,
    "private_isolation_passed": false,
    "read_audit_available": false
  },
  "governance": {
    "proposal_id": null,
    "status": "not_started|open|passed|rejected|blocked",
    "for": 0,
    "against": 0,
    "constitution_version_before": 1,
    "constitution_version_after": 1,
    "adapter_connected": true
  },
  "economy": {
    "pitches": 0,
    "syntax_valid_urls": 0,
    "resolvable_artifacts": 0,
    "resolver_status": "local_reference_contract_only"
  },
  "blockers": ["blog_read_reference_audit", "external_content_verification", "real_llm_run_pending_user_confirmation"],
  "claim_strength": "implementation_contract_only"
}
```

---

## 20. 实现顺序与代码验收映射

| 顺序 | 代码位置 / 变更 | 测试 | 完成后可以声称什么 |
|---:|---|---|---|
| 1 | `EWToolSpace` 和专用环境增加 `enabled_tools` 白名单 | 目录、重复注册、未知名拒绝 | 场景确实暴露 29 个公共工具 |
| 2 | Social router 将 `read_messages` 接到 `receive_messages` | send→read→log round-trip | 私信链路可复算 |
| 3 | Governance adapter 统一 proposal id 和 state | 4/5 through、重复票、final report | 代码契约层的治理状态可用 |
| 4 | BlogSpace 增加 `case_id` / artifact refs | public/private、draft/published、restore | Blog 可作为结构化公共 artifact |
| 5 | Blog read/reference audit | read event、Billboard 引用、pitch 引用 | 待后续实现后再讨论完整传播链 |
| 6 | Economy evidence resolver | URL syntax / artifact resolution 分离 | 当前可区分本地引用和外部内容待解析 |
| 7 | 创建 `scenarios/public_information_crisis.yaml` | YAML validate + config build | 场景可被 afi CLI 组装 |
| 8 | 单 seed `evidence_first` | run + replay + audit | 机制级 pilot 跑通 |
| 9 | 单 seed `rumor_first` | same seed/control checks | 可以比较传播顺序 |
| 10 | 多 seed、多模型 | 3 seeds × 2 variants × 2 models | 才能开始讨论趋势性差异 |

### 当前阶段明确结论

截至本次文档修订，场景处于 **pilot-implementation-ready**：

- 场景定义、工具规划和工具参数样例完整；
- `enabled_tools` exact allowlist 已接入场景 builder；
- 29 个公共工具已按唯一 owner 挂载到 7 个环境；
- `read_messages` 已接通 Social mailbox，8 个治理 alias 已接通 GovernanceSpace；
- Blog / proposal / pitch 已具备 PIC-001 的最小 case/artifact metadata；
- 已创建正式场景 YAML、fixture、专项单元/集成测试；
- 尚未运行真实 LLM PIC-001，不应把代码契约测试写成传播率、治理率或事实核验结果；
- Economy 本地 resolver 验证的是 artifact reference 形状和映射，不是外部内容真实性。

---

## 21. 版本记录补充

| 日期 | 变更 |
|---|---|
| 2026-07-30 | 完成 PIC-001 最小实现：exact tool allowlist、Social mailbox adapter、8 个 Governance alias、Blog/Economy case/artifact metadata、正式 YAML/fixture 和专项测试；不运行真实 LLM、不提交 Git。 |
| 2026-07-27 | 根据用户反馈补充实现级场景规格：固定 PIC-001 元数据、初始状态、case brief、逐 step/Agent 调用计划、30 个参数样例、状态机、不变量、artifact 关联和运行结束报告结构；仍不提交 Git、不运行正式场景。 |
| 2026-07-27 | 将 PIC-001 接入独立场景目录，补充地图/空间边界和 5 个地标的核心因果用途。 |
