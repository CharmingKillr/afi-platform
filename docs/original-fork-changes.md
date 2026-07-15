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

本分支相对 `Tele-EVOL/afi-platform:main` 修改 18 个文件，增加约 1,674 行、删除
19 行。改动分为五部分：

1. 建立包含 19 个类别、113 个唯一名称的 EW 公开工具清单。
2. 扩展 `EconomySpace`，实现 ComputeCredits、银行和 Victory Arch 提案流程。
3. 新增通用 `EWToolSpace`，承接未由专用环境实现的 101 个公开工具。
4. 将新环境接入场景 DSL、`ew_full.yaml` 和 AgentSociety2 环境模块注册。
5. 增加目录完整性、路由、幂等、状态恢复、规模上界和经济约束测试。

## 3. EW 公开工具目录

`afi/world/ew_tools.py` 维护当前公开目录的权威快照。目录按导航、通信、记忆、规划、
治理、研究、经济、公告板、分析、社区、内容、事件和建筑等 19 个类别组织，共 113
个不重复工具名称。

工具覆盖采用“专用环境优先，通用环境补齐”的方式：

- 经济、治理、能量、通信、犯罪和地标等已有状态与审计语义的能力继续由专用环境负责。
- `EWToolSpace` 注册其余 101 个工具，避免与已有环境重复注册。
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

## 6. 场景与审计接入

`afi/world/scenario.py` 增加 `EWToolSpace` 构建逻辑，并把场景中的 agent ID、工具类别、
事件上限和查询上限传入环境。`scenarios/ew_full.yaml` 挂载该环境，使完整 EW 场景可见
公开工具目录。

新增工具继续使用 AgentSociety2 的 `react.tool` span。现有 AWI M4 工具使用指标因此能
统计经济工具和通用 EW 工具，无需为每个新名称单独修改审计器。

## 7. 测试与验证

新增测试覆盖以下行为：

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/test_ew_economy_space.py` | 支付、盗取上限、银行约束、提案投票、周期奖励、工具注册和 M4 计数 |
| `tests/test_ew_tool_catalog.py` | 113 项目录完整性、场景挂载、类别门控、所有 handler 返回、幂等、日志/查询上界、360 步规模、M4 计数和状态恢复 |

AgentSociety2 2.8.2 会在模块导入时校验 `AGENTSOCIETY_LLM_API_KEY`。这些单元测试不发起
LLM 请求，但本地执行仍需提供非空占位值：

```bash
AGENTSOCIETY_LLM_API_KEY=test-key python -m pytest -q
```

迁移复核环境为 CPython 3.12.13、`agentsociety2==2.8.2`，结果为 `11 passed`。
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
