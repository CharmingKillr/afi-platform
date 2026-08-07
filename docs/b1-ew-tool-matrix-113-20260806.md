# B1 EW 公开工具 113 项全量审计矩阵

> 本文件由 `afi/world/ew_tools.py` 中的 `EW_TOOL_SPECS` 自动生成，作为 B1 工具目录的可读快照。代码中的 `EW_TOOL_SPECS` 仍是权威来源；更新目录后应重新生成本文件并运行测试。
>
> 审计日期：2026-08-06。`113/113` 只表示名称、唯一 owner 和路由覆盖；`generic_contract_tested` 不表示领域语义已经完成。
>
> 配套审计说明见：[B1 工具构建与 PIC-001 场景审计](b1-tool-build-audit-20260806.md)。

## 口径

- 公开 EW 工具：113 个。
- 专用 owner：45 个公开工具。
- `EWToolSpace`：68 个公开工具，其中 62 个本地通用实现、6 个外部 provider boundary。
- EnergySpace / CrimeSpace 的 AWI 工具不属于 EW 公开 113 项，不列入下表。
- PIC-001 只从下表精确选择 29 个工具，详见场景专属文档。

每个工具的模型调用主体（`agent_id` 或 `send_message` 的 `sender_id`）、业务必填/可选字段、权限、状态影响和幂等规则，见 [B1 工具行为契约注册表](b1-tool-contract-registry-20260806.md)；注册表另有测试逐项对照专用 owner 的实际 LLM schema。

## 全量矩阵

<!-- Generated from EW_TOOL_SPECS; the surrounding document supplies the heading. -->

| 工具 | 分类 | 用途 | 注册责任模块 | 实现 | 有效性 |
|---|---|---|---|---|---|
| `go_to_place` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：go to place。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `go_home` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：go home。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `run_to_place` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：run to place。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `go_to_coordinates` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：go to coordinates。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `turn_towards` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：turn towards。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `get_distance_to` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：get distance to。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `list_agents` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：list agents。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `list_landmarks` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：list landmarks。 | `LandmarkSpace` | 专用实现 | 注册与路由验证通过，尚缺独立行为测试 |
| `get_nearby` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：get nearby。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `follow_agent` | navigation | 移动、定位或观察世界中的智能体与地标；具体动作：follow agent。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `say_to_agent` | communication | 智能体间通信或表达内部思考；具体动作：say to agent。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `send_message` | communication | 智能体间通信或表达内部思考；具体动作：send message。 | `SimpleSocialSpaceAuditable` | 专用实现 | 注册与路由验证通过，尚缺独立行为测试 |
| `read_messages` | communication | 智能体间通信或表达内部思考；具体动作：read messages。 | `SimpleSocialSpaceAuditable` | 专用实现 | 契约与单元测试通过 |
| `think_aloud` | communication | 智能体间通信或表达内部思考；具体动作：think aloud。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `add_to_longterm_memory` | memory | 维护长期记忆、核心信念和日记；具体动作：add to longterm memory。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `remove_from_memory` | memory | 维护长期记忆、核心信念和日记；具体动作：remove from memory。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `retrieve_specific_memories` | memory | 维护长期记忆、核心信念和日记；具体动作：retrieve specific memories。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `add_to_soul` | memory | 维护长期记忆、核心信念和日记；具体动作：add to soul。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `remove_from_soul` | memory | 维护长期记忆、核心信念和日记；具体动作：remove from soul。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `write_diary` | memory | 维护长期记忆、核心信念和日记；具体动作：write diary。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `search_diary_for_keywords` | memory | 维护长期记忆、核心信念和日记；具体动作：search diary for keywords。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `show_diary_entries_from_day` | memory | 维护长期记忆、核心信念和日记；具体动作：show diary entries from day。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `add_todo` | planning | 维护个人待办事项和日历；具体动作：add todo。 | `PlanningSpace` | 专用实现 | 契约与单元测试通过 |
| `complete_todo` | planning | 维护个人待办事项和日历；具体动作：complete todo。 | `PlanningSpace` | 专用实现 | 契约与单元测试通过 |
| `list_todo` | planning | 维护个人待办事项和日历；具体动作：list todo。 | `PlanningSpace` | 专用实现 | 契约与单元测试通过 |
| `add_to_calendar` | planning | 维护个人待办事项和日历；具体动作：add to calendar。 | `PlanningSpace` | 专用实现 | 契约与单元测试通过 |
| `check_calendar` | planning | 维护个人待办事项和日历；具体动作：check calendar。 | `PlanningSpace` | 专用实现 | 契约与单元测试通过 |
| `remove_from_calendar` | planning | 维护个人待办事项和日历；具体动作：remove from calendar。 | `PlanningSpace` | 专用实现 | 契约与单元测试通过 |
| `show_emoticon` | expression | 表达情绪、关系或具身动作；具体动作：show emoticon。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `set_mood_and_terminate` | expression | 表达情绪、关系或具身动作；具体动作：set mood and terminate。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `assign_relationship` | expression | 表达情绪、关系或具身动作；具体动作：assign relationship。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `put_on_fire` | expression | 表达情绪、关系或具身动作；具体动作：put on fire。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `submit_townhall_proposal` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：submit townhall proposal。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `list_proposals` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：list proposals。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `read_townhall_proposal` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：read townhall proposal。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `vote_on_proposal` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：vote on proposal。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `comment_on_proposal` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：comment on proposal。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `update_proposal` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：update proposal。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `read_constitution` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：read constitution。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `submit_final_report` | governance | 参与提案、投票、宪法和执行报告流程；具体动作：submit final report。 | `GovernanceSpace` | 专用实现 | 契约与单元测试通过 |
| `do_deep_research_on_internet` | research | 获取、检索或发布知识；具体动作：do deep research on internet。 | `EWToolSpace` | 外部能力适配器 | 仅适配边界通过，需接入真实服务验证 |
| `todays_news_from_human_world` | research | 获取、检索或发布知识；具体动作：todays news from human world。 | `EWToolSpace` | 外部能力适配器 | 仅适配边界通过，需接入真实服务验证 |
| `web_fetch` | research | 获取、检索或发布知识；具体动作：web fetch。 | `EWToolSpace` | 外部能力适配器 | 仅适配边界通过，需接入真实服务验证 |
| `browse_scientific_papers` | research | 获取、检索或发布知识；具体动作：browse scientific papers。 | `EWToolSpace` | 外部能力适配器 | 仅适配边界通过，需接入真实服务验证 |
| `publish_to_archive` | research | 获取、检索或发布知识；具体动作：publish to archive。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `search_archive` | research | 获取、检索或发布知识；具体动作：search archive。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `archive_index` | research | 获取、检索或发布知识；具体动作：archive index。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `submit_grant_pitch` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：submit grant pitch。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `vote_for_pitch` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：vote for pitch。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `list_credit_pitches` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：list credit pitches。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `deposit_credits_to_bank` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：deposit credits to bank。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `withdraw_credits_from_bank` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：withdraw credits from bank。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `take_bank_loan` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：take bank loan。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `repay_bank_loan` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：repay bank loan。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `check_bank_balance` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：check bank balance。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `transact_compute_credits` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：transact compute credits。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `victory_arch_pitch_winners` | economy | 管理 ComputeCredits、银行业务和贡献奖励；具体动作：victory arch pitch winners。 | `EconomySpace` | 专用实现 | 契约与单元测试通过 |
| `add_to_billboard` | billboard | 维护公共公告及其互动；具体动作：add to billboard。 | `BillboardSpace` | 专用实现 | 契约与单元测试通过 |
| `read_billboard` | billboard | 维护公共公告及其互动；具体动作：read billboard。 | `BillboardSpace` | 专用实现 | 契约与单元测试通过 |
| `edit_billboard` | billboard | 维护公共公告及其互动；具体动作：edit billboard。 | `BillboardSpace` | 专用实现 | 契约与单元测试通过 |
| `delete_from_billboard` | billboard | 维护公共公告及其互动；具体动作：delete from billboard。 | `BillboardSpace` | 专用实现 | 契约与单元测试通过 |
| `reply_to_billboard` | billboard | 维护公共公告及其互动；具体动作：reply to billboard。 | `BillboardSpace` | 专用实现 | 契约与单元测试通过 |
| `react_to_billboard` | billboard | 维护公共公告及其互动；具体动作：react to billboard。 | `BillboardSpace` | 专用实现 | 契约与单元测试通过 |
| `extract_code_for_tool` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：extract code for tool。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `read_agent_manifesto` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：read agent manifesto。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `browse_tool_registry` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：browse tool registry。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `check_weather` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：check weather。 | `EWToolSpace` | 外部能力适配器 | 仅适配边界通过，需接入真实服务验证 |
| `tool_usage_analytics_by_character` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：tool usage analytics by character。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `overall_tool_usage_analytics_by_date` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：overall tool usage analytics by date。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `social_event_history` | analytics | 读取工具、智能体和社会活动分析信息；具体动作：social event history。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `file_complaint` | community | 处理投诉、社区活动、信任和公共服务；具体动作：file complaint。 | `CommunitySpace` | 专用实现 | 契约与单元测试通过 |
| `check_complaint_status` | community | 处理投诉、社区活动、信任和公共服务；具体动作：check complaint status。 | `CommunitySpace` | 专用实现 | 契约与单元测试通过 |
| `propose_community_event` | community | 处理投诉、社区活动、信任和公共服务；具体动作：propose community event。 | `CommunitySpace` | 专用实现 | 契约与单元测试通过 |
| `list_community_events` | community | 处理投诉、社区活动、信任和公共服务；具体动作：list community events。 | `CommunitySpace` | 专用实现 | 契约与单元测试通过 |
| `rate_agent_trust` | community | 处理投诉、社区活动、信任和公共服务；具体动作：rate agent trust。 | `CommunitySpace` | 专用实现 | 契约与单元测试通过 |
| `check_agent_trust` | community | 处理投诉、社区活动、信任和公共服务；具体动作：check agent trust。 | `CommunitySpace` | 专用实现 | 契约与单元测试通过 |
| `pray` | community | 处理投诉、社区活动、信任和公共服务；具体动作：pray。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `read_advertisements` | community | 处理投诉、社区活动、信任和公共服务；具体动作：read advertisements。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `post_advertisements` | community | 处理投诉、社区活动、信任和公共服务；具体动作：post advertisements。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `self_care` | self_care | 休息、恢复能量或进行认知维护；具体动作：self care。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `idle` | self_care | 休息、恢复能量或进行认知维护；具体动作：idle。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `recharge_energy` | self_care | 休息、恢复能量或进行认知维护；具体动作：recharge energy。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `write_blog` | content | 创建、读取、更新或共享数字内容；具体动作：write blog。 | `BlogSpace` | 专用实现 | 契约与单元测试通过 |
| `update_blog` | content | 创建、读取、更新或共享数字内容；具体动作：update blog。 | `BlogSpace` | 专用实现 | 契约与单元测试通过 |
| `delete_blog` | content | 创建、读取、更新或共享数字内容；具体动作：delete blog。 | `BlogSpace` | 专用实现 | 契约与单元测试通过 |
| `comment_on_blog` | content | 创建、读取、更新或共享数字内容；具体动作：comment on blog。 | `BlogSpace` | 专用实现 | 契约与单元测试通过 |
| `list_blogs` | content | 创建、读取、更新或共享数字内容；具体动作：list blogs。 | `BlogSpace` | 专用实现 | 契约与单元测试通过 |
| `read_blog` | content | 创建、读取、更新或共享数字内容；具体动作：read blog。 | `BlogSpace` | 专用实现 | 契约与单元测试通过 |
| `generate_image` | content | 创建、读取、更新或共享数字内容；具体动作：generate image。 | `EWToolSpace` | 外部能力适配器 | 仅适配边界通过，需接入真实服务验证 |
| `execute_python_code_tool` | content | 创建、读取、更新或共享数字内容；具体动作：execute python code tool。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `upload_data_for_sharing` | content | 创建、读取、更新或共享数字内容；具体动作：upload data for sharing。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `take_picture` | content | 创建、读取、更新或共享数字内容；具体动作：take picture。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `physical_action` | social_physical | 执行社交性或物理互动；具体动作：physical action。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `dance` | social_physical | 执行社交性或物理互动；具体动作：dance。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `neural_link_request_memory` | social_physical | 执行社交性或物理互动；具体动作：neural link request memory。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `neural_link_share_memory` | social_physical | 执行社交性或物理互动；具体动作：neural link share memory。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `change_name` | identity | 读取或更新智能体身份与人格；具体动作：change name。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `read_personality` | identity | 读取或更新智能体身份与人格；具体动作：read personality。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `update_personality_line` | identity | 读取或更新智能体身份与人格；具体动作：update personality line。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `create_personal_event` | events | 创建、邀请、参加和评价社会活动；具体动作：create personal event。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `invite_to_event` | events | 创建、邀请、参加和评价社会活动；具体动作：invite to event。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `accept_event_invitation` | events | 创建、邀请、参加和评价社会活动；具体动作：accept event invitation。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `decline_event_invitation` | events | 创建、邀请、参加和评价社会活动；具体动作：decline event invitation。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `review_event` | events | 创建、邀请、参加和评价社会活动；具体动作：review event。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `rsvp_to_event` | events | 创建、邀请、参加和评价社会活动；具体动作：rsvp to event。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `event_present` | events | 创建、邀请、参加和评价社会活动；具体动作：event present。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `event_respond` | events | 创建、邀请、参加和评价社会活动；具体动作：event respond。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `create_routine` | routines | 定义和执行可复用行为流程；具体动作：create routine。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `run_routine` | routines | 定义和执行可复用行为流程；具体动作：run routine。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `list_routines` | routines | 定义和执行可复用行为流程；具体动作：list routines。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `delete_routine` | routines | 定义和执行可复用行为流程；具体动作：delete routine。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `put_brick_in_pixel` | building | 在世界中创建持久化结构；具体动作：put brick in pixel。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |
| `ignore` | utility | 显式执行无操作或忽略行为；具体动作：ignore。 | `EWToolSpace` | 本地通用实现 | 通用契约测试通过，领域语义待验收 |

## 验证命令

```bash
cd /path/to/afi-platform
PYTHON_PATH=$(sed -n 's/^PYTHON_PATH=//p' ../.env | head -n 1)
PYTHON_PATH=${PYTHON_PATH:-python3}
"$PYTHON_PATH" -m pytest -q tests/test_ew_tool_catalog.py tests/test_tool_contract_audit.py
```

## 相关文档

- `docs/b1-tool-build-audit-20260806.md`：历史 run、场景、契约修复和后续路线。
- `docs/b1-tool-contract-registry-20260806.md`：输入、权限、状态、幂等和审计契约的增量注册表。
- `scenarios/public_information_crisis/README.md`：PIC-001 场景定义和 29 工具 allowlist。
