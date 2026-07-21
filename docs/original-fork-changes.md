# 原 Fork 改动整理：EW 公开工具目录与经济环境扩展

## 1. 文档目的

本文整理此前在 `CharmingKillr/afi-platform`（原上游为
`zhangjun221/afi-platform`）完成、现已迁移到新 Fork 的改动。新 Fork 基于
`Tele-EVOL/afi-platform`，功能分支为 `codex/b1-ew-complete_jw`。

迁移的代码由以下两个提交组成：

| 提交 | 内容 |
|---|---|
| `c0ea909` | 增加 EW ComputeCredits 经济工具批次 |
| `4756300` | 补齐当前公开的 EW 工具目录并完成验证 |

这些改动的目标不是复制 Emergence World 的实现，而是按照其公开工具名称和语义，
在 AgentSociety2 的自定义环境机制上完成独立实现，使 afi-platform 能覆盖更完整的
社会模拟动作面，并让工具行为进入现有 trace、AWI 和审计流程。

## 2. 改动总览

本分支相对 `Tele-EVOL/afi-platform:main` 修改 16 个文件，增加约 1,671 行、删除
19 行。改动分为五部分：

1. 建立包含 19 个类别、113 个唯一名称的 EW 公开工具清单。
2. 扩展 `EconomySpace`，实现 ComputeCredits、银行和 Victory Arch 提案流程。
3. 新增通用 `EWToolSpace`；在 PR #1/#2 整合后承接未由专用环境实现的 95 个公开工具。
4. 将新环境接入场景 DSL、`ew_full.yaml` 和 AgentSociety2 环境模块注册。
5. 增加目录完整性、路由、幂等、状态恢复、规模上界和经济约束测试。

### 2.1 一句话说明贡献

改动前，平台虽然能运行 EW 风格的治理、能量、犯罪和基础经济场景，但大部分 EW 公开
工具没有可调用实现：agent 不能真正写博客、维护日历、创建事件、管理记忆、评价信任、
使用公告板或调用完整 ComputeCredits 流程。

改动后，平台获得了覆盖当前 113 项公开名称的工具层：18 项由专用环境负责，其中
`PlanningSpace` 提供 6 项规划工具；`EWToolSpace` 提供其余 95 项。工具拥有可恢复状态、权限与容量约束，并进入 replay 和
AWI 工具使用统计。经济环境同时从简单余额字段扩展为可运行的支付、盗取、银行、提案、
投票和周期奖励系统。

### 2.2 可直接运行的 Demo

无需调用真实 LLM，可直接运行确定性演示：

```bash
AGENTSOCIETY_LLM_API_KEY=demo-key python demo/ew_tool_adaptation_demo.py
```

Demo 依次展示：

1. 113 项公开工具由 95 项通用工具和 18 项专用工具组成。
2. 只启用 navigation + memory 时，模型工具面从 95 项缩减到 17 项。
3. 记忆写入会改变环境状态，同一步重复请求不会重复插入。
4. 一个 agent 不能修改另一个 agent 创建的博客。
5. 论文搜索返回 provider request，不伪造论文；代码工具阻止 import/system 调用。
6. 保存并恢复后，记忆仍存在，工具路由器仍可使用。
7. 经济系统限制盗取最多 10 CC、拒绝 4 CC 贷款、允许 3 CC 贷款、禁止自投，并在
   两个模拟日后向获胜提案发放 20 CC。

## 3. EW 公开工具目录

`afi/world/ew_tools.py` 维护当前公开目录的权威快照。目录按导航、通信、记忆、规划、
治理、研究、经济、公告板、分析、社区、内容、事件和建筑等 19 个类别组织，共 113
个不重复工具名称。

工具覆盖采用“专用环境优先，通用环境补齐”的方式：

- 经济、治理、能量、通信、犯罪和地标等已有状态与审计语义的能力继续由专用环境负责。
- `EWToolSpace` 注册其余 95 个工具，规划类 6 个工具由 `PlanningSpace` 专用实现，避免重复注册。
- `enabled_categories` 可按场景只开放部分工具，减少模型路由表面积。
- 需要实时互联网、新闻、科学论文或外部执行器的工具返回 provider 请求，而不是伪造外部结果。

这里的“113/113”仅指 2026-07-15 检查到的公开工具表，不代表 EW 私有运行时或后续
版本中提到的“120+”工具已经全部实现。

## 4. 通用 EWToolSpace

`custom/envs/ew_tool_space.py` 提供可热加载的 AgentSociety2 自定义环境，主要补充：

- 导航、记忆、待办、日历、社区、博客、事件、例程、人格与关系等领域状态。
- 工具调用统一返回结构化状态，写操作具有明确的 `success`、`fail`、`in_progress`
  或 `error` 结果。
- 同一步骤内的重复写入进行幂等去重，避免重试造成重复副作用。
- 事件日志和查询结果设置上限，支持长时程与较大 agent 数量的模拟。
- `to_workspace` / `restore` 持久化领域状态，同时保留 AgentSociety2 生成的工具路由器。
- 对未连接的外部能力使用显式 provider 请求，保持可审计和可替换。

环境元数据写入 `.agentsociety/env_modules/ewtoolspace.json`，并提供
`custom/envs/ew_tool_space_agent_skills/ew-world-tools/SKILL.md`，供 AgentSociety2
扫描、注册和向 agent 暴露工具使用规则。

### 4.1 EW 工具的具体适配链路

一次 EW 工具调用从配置到审计经过以下步骤：

1. `afi/world/ew_tools.py` 保存公开工具名称及类别，用于覆盖率检查。
2. `EWToolSpace` 类定义结束前遍历工具目录，跳过 `SPECIALIZED_TOOLS` 中已经由
   EconomySpace、LandmarkSpace 或消息环境实现的名称。
3. `_make_catalog_tool()` 为每个剩余名称创建独立的异步方法，写入正确的
   `__name__`、docstring 和函数签名，并应用 AgentSociety2 的 `@tool` 装饰器。
4. 这些方法在 `EnvMeta` 创建类之前进入 `EWToolSpace` 的类命名空间，因此
   AgentSociety2 的 CodeGenRouter 会把它们识别为普通、独立命名的工具，而不是一个
   只能在运行时解释的通用入口。
5. 模型通过 `ask_environment` 选择具体工具名，并传入 `agent_id` 与 `request`。
   动态方法把请求转交给 `_dispatch(tool_name, agent_id, request)`。
6. `_dispatch()` 根据工具领域执行导航、记忆、内容、关系、事件等状态机逻辑，或为
   未接入的实时外部能力返回可关联的 provider request。
7. 写操作通过 `_write_once()` 执行；它记录事件、更新工具使用次数，并对同一步骤内
   完全相同的请求进行幂等去重。
8. 每个模拟 step 把 agent 摘要和环境摘要写入 AgentSociety2 replay state。正常
   `react.tool` span 同时记录具体工具名称，因此现有 AWI M4 可直接统计新增工具。

动态生成只减少重复的注册样板，不会把所有工具实现成同一种行为。真正的领域差异仍在
`_dispatch()` 中显式维护。

### 4.2 新增的领域状态

`EWToolSpace.__init__()` 增加了以下主要状态：

| 状态 | 用途 |
|---|---|
| `_positions`、`_follows`、`_facing` | 位置、跟随和朝向 |
| `_mailboxes` | EWToolSpace 内的近距离消息读取；直接消息仍由专用环境负责 |
| `_memories`、`_souls`、`_diaries` | 长期记忆、soul 信息和日记 |
| `_todos`、`_calendars` | 待办与日历 |
| `_moods`、`_personalities` | 情绪和人格描述 |
| `_relationships`、`_trust` | 关系类型与信任评分 |
| `_billboard`、`_blogs`、`_archive` | 公告板、博客和研究档案 |
| `_complaints`、`_proposals`、`_events` | 投诉、提案和公共/个人事件 |
| `_routines`、`_advertisement`、`_uploads`、`_bricks` | 例程、广告、共享数据和像素建筑 |
| `_event_log`、`_usage` | 有界事件历史和按工具/agent 聚合的使用次数 |
| `_dedup` | 当前 step 的写操作幂等缓存 |

状态更新由 `asyncio.Lock` 串行保护。事件历史最多保留 `max_events` 条，查询最多返回
`max_query_items` 条；配置值还带有最小和最大边界，避免场景误配置导致无限增长。

### 4.3 工具行为如何分组实现

`_dispatch()` 没有为每个工具复制一整套 CRUD，而是按共享语义复用小型状态操作：

- 导航工具更新 `_positions`，距离查询根据坐标计算，附近 agent 根据当前 place 判断。
- 记忆、日记、待办和日历复用 `_add_item()` / `_remove_item()`，并支持 query/date 过滤。
- 公告、博客、档案、投诉、提案、事件和例程复用 `_create_record()`、
  `_update_record()`、`_delete_record()`，修改和删除检查 owner。
- 关系和信任使用带双方 ID 的索引键；评分被限制在 1 到 5。
- 广告带 `expires_step`，在 step 推进时自动过期。
- `execute_python_code_tool` 只接受 AST 校验后的字面量和算术表达式，禁用 builtins，
  并不是通用 Python 执行器。
- 搜索、新闻、网页、论文、天气和图像生成不伪造结果，而是返回
  `status=in_progress`、确定性 `request_id` 和 provider queue 提示。
- 不认识的名称明确返回 `status=error`，覆盖测试确保当前注册目录不存在这种情况。

### 4.4 类别门控与恢复

场景可通过 `world.ew_tool_categories` 只启用部分类别。构造函数同步过滤
`ToolManager`、LLM tool schema 和 readonly schema，因此被禁用的工具不会继续出现在
模型可选工具列表里。

`to_workspace()` 只保存可序列化的领域状态，不保存锁、ToolManager、replay writer
或 LLM schema 等运行时对象。`restore()` 恢复 JSON 后重建整数键和锁，保留构造阶段
已经生成的工具路由器，避免 resume 后工具列表被持久化数据覆盖。

## 5. EconomySpace 扩展

`custom/envs/economy_space.py` 在原有经济状态上增加 EW 风格的 ComputeCredits 流程：

- agent 间支付与受限盗取；盗取额度受规则约束，不能任意转移余额。
- Central Bank 存款、取款、贷款、还款和余额查询。
- agent 技能、收入、消费字段的读取和更新。
- Victory Arch grant pitch 的提交、投票、周期结算和获胜者查询。
- 防止给自己的提案投票，并限制同一投票者在同一周期的重复投票。
- 周期结束后根据投票结果发放奖励，并保留可查询的结算记录。

`scenarios/ew-economic-smoke.yaml` 提供两名 agent 的最小经济流程，依次验证支付、存款、
贷款、提案、投票和余额查询。

### 5.1 经济环境新增了什么代码

经济环境新增钱包、银行和提案周期三组持久状态：

- `_persons` 保存 wallet、skill、income 和 consumption。
- `_deposits` 与 `_loans` 分别保存银行存款和贷款余额。
- `_pitches`、`_pitch_history`、`_pitch_cycle` 与 `_next_pitch_close` 管理 Victory
  Arch 的当前提案、历史结算和模拟时间周期。
- `_transactions` 保存支付、盗取及其他经济流水的 actor、target、amount、step 和时间。

`step()` 按经过的模拟天数结算收入减消费、存款利息和贷款利息，并在跨过周期结束时间时
调用 `_close_pitch_cycle()`。合格提案按票数、提交顺序和 ID 排序，前三名获得
20/10/10 ComputeCredits。

新增的 EW 经济工具包括：

| 工具组 | 新增工具与约束 |
|---|---|
| 转账 | `transact_compute_credits` 支持 `pay` 和显式犯罪的 `steal`；禁止给自己转账，盗取单次最多 10 CC |
| 提案 | `submit_grant_pitch` 要求证据 URL；每人每周期一个提案 |
| 投票 | `vote_for_pitch` 禁止自投，并限制每人每周期一票 |
| 查询 | `list_credit_pitches`、`victory_arch_pitch_winners` |
| 银行 | 存款、取款、1 到 3 CC 小额贷款、还款和余额查询 |
| AS 兼容 | 保留 `get_person*`、`add_person_currency`、income/consumption 读写接口 |

经济状态通过 `to_workspace()` 写入同一环境状态文件，并在 `restore()` 中恢复整数 agent
键、时间字段、交易记录和 pitch 周期，支持中断后继续运行。

## 6. 场景与审计接入

`afi/world/scenario.py` 增加 `EWToolSpace` 构建逻辑，并把场景中的 agent ID、工具类别、
事件上限和查询上限传入环境。`scenarios/ew_full.yaml` 挂载该环境，使完整 EW 场景可见
公开工具目录。

新增工具继续使用 AgentSociety2 的 `react.tool` span。现有 AWI M4 工具使用指标因此能
统计经济工具和通用 EW 工具，无需为每个新名称单独修改审计器。

具体配置过程如下：

- `scenario.py::_env_builders()` 新增 `EWToolSpace` builder。
- builder 注入 agent ID/名称、home、landmark、manifesto、constitution，以及事件和
  查询上限。
- `scenarios/ew_full.yaml` 在原有治理、经济、社交、地标、能量和犯罪环境后挂载
  `EWToolSpace`。
- `.agentsociety/env_modules/ewtoolspace.json` 告诉 AgentSociety2 自定义模块的位置和
  初始化说明；其中路径使用仓库相对路径，避免绑定开发者本机目录。
- `ew-world-tools/SKILL.md` 告诉 agent 使用精确工具名、统一 request 字段，以及写操作
  幂等和查询上限。

## 7. 测试与验证

新增测试覆盖以下行为：

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/test_ew_economy_space.py` | 支付、盗取上限、银行约束、提案投票、周期奖励、工具注册和 M4 计数 |
| `tests/test_ew_tool_catalog.py` | 113 项目录完整性、场景挂载、元数据路径可移植性、类别门控、所有 handler 返回、幂等、日志/查询上界、360 步规模、M4 计数和状态恢复 |

AgentSociety2 2.8.2 会在模块导入时校验 `AGENTSOCIETY_LLM_API_KEY`。这些单元测试不发起
LLM 请求，但本地执行仍需提供非空占位值：

```bash
AGENTSOCIETY_LLM_API_KEY=test-key python -m pytest -q
```

迁移复核环境为 CPython 3.12.13、`agentsociety2==2.8.2`，结果为 `12 passed`。
环境扫描、测试和注册均通过；对应的 `.agentsociety/custom_env_skill/runs/` 生成产物
未纳入 PR，避免把一次性运行记录提交到版本库。

## 8. 明确边界与未完成项

- 工具名称和公开语义得到覆盖，不等于复现 EW 私有后端或所有实时数据源。
- provider 类工具仍需配置真实搜索、新闻、论文、图像或代码执行服务。
- 113 项是公开目录快照；上游目录变化后需要更新清单和覆盖测试。
- 当前测试验证状态机、注册和规模边界，不替代 10 agent、360 tick、多模型的完整运行测试。
- M3 地图、M6 公开表达和 M7 关系类型仍存在平台原有的指标保真度缺口。

## 9. 迁移后的协作方式

- 新上游：`Tele-EVOL/afi-platform`
- 个人 Fork：`CharmingKillr/afi-platform`
- 功能分支：`codex/b1-ew-complete_jw`
- 旧仓库备份：`CharmingKillr/afi-platform-legacy`

后续开发应从新上游同步 `main`，在个人 Fork 的功能分支提交，并通过 Pull Request 合入
`Tele-EVOL/afi-platform`。旧仓库只作为历史备份，不再承接新开发。
