# afi-platform 平台搭建进展总结（规划 vs 实际）

> 2026-07-14。聚焦**平台搭建（A1-A4）**的进展总结：规划做什么、实际做到哪、还差什么。
> 数据来自代码与文档实测（`architecture-and-roadmap.md` 路线、`technical-architecture.md` §12 完成度、`afi/` 模块、`custom/envs/`、`runs/` 均核实），非凭记忆。
> 范围限定平台本身；旗舰方法（第一骨牌归因/反事实）不在此文。

> **2026-07-27 更新**：B1 内容领域继续推进，新增 `BlogSpace`，将 6 个内容工具从 `EWToolSpace` 拆出并完成严格契约、权限、状态、幂等、恢复和测试；当前分支测试为 25 passed。原文中的 7 月 14 日数字保留作为历史基线，当前口径以本更新和 `docs/blog-space-implementation.md` 为准。
> **2026-08-06 工具审计基线（Billboard 拆分前）**：按当时工作树复核的 113 个公开工具 owner 分布为 33 个专用实现、80 个 `EWToolSpace` 承载，其中 74 个是本地通用实现、6 个是外部能力 provider boundary；另有 EnergySpace 6 个、CrimeSpace 3 个 AWI 专用工具不计入 EW 公开目录。该基线的工具契约审计覆盖 Energy/Crime/Social/Governance，相关测试为 44 passed；真实 LLM 验证本次未启动。当前口径以紧随其后的 B4 更新为准。
> **2026-08-06 B4 更新**：Billboard 6 个公开工具已拆为独立 `BillboardSpace`，当前 owner 分布调整为 39 个专用实现、74 个 `EWToolSpace` 承载（68 个 generic local、6 个 provider boundary）。新增 typed 参数、owner/parent-child、case/evidence metadata、soft-delete、事件日志、replay/restore 和 AWI M6 public-expression 读取；本地测试已扩展为 45 项，真实 LLM 验证仍未启动。
> **2026-08-06 B5 更新**：Community 6 个公开工具已拆为独立 `CommunitySpace`，当前 owner 分布调整为 45 个专用实现、68 个 `EWToolSpace` 承载（62 个 generic local、6 个 provider boundary）。新增投诉/社区活动/trust 状态、摘要权限、行为契约注册表、事件日志和 replay/restore；PIC-001 deterministic 当前仍为 29/29、43 calls、0 failures、pass=true；全量离线测试 118 passed，真实 LLM 验证仍未启动。
> **2026-08-06 B6 契约精度更新**：复核 PR #2 的 typed/replayable 设计后，修正 `GovernanceSpace`/`read_messages` 的 envelope 登记，补齐专用领域工具的 required/optional fields；Community 的 `artifact_id` 已进入状态、事件、trust 摘要和 restore，审计 event id 改为单调递增。针对性回归 35 passed，PIC-001 deterministic 复跑保持 29/29、43 calls、0 failures、pass=true；未启动新的 LLM 验证。
> **2026-08-06 B7 schema parity 更新**：进一步对照实际模型可见的 `_llm_tools` schema，补齐 `send_message.sender_id`、`check_calendar.limit`、`transact_compute_credits.mode`，并将主体字段从业务字段中独立建模；新增 `validate_tool_arguments()` 和专用 owner schema parity 测试。全量离线测试 `119 passed`，针对性回归 `36 passed`；该更新只增强契约前置校验，不改变 PIC-001 的 29 工具面，也未启动新的 LLM 验证。
> **2026-08-06 B8 generic domain slice 更新**：在保持 113/113 目录和路由不变的基础上，进一步完善 62 个 generic 工具的第一轮领域状态路径：导航坐标/目标校验、记忆/日记查询、个人事件邀请与 RSVP、routine owner/运行记录、archive 检索索引、结构化上传 checksum、neural link、能量与动作审计，并补充 replay/restore 回归。全量离线测试 `121 passed`；真实地图、Provider 和 LLM 自主验证仍未启动。
> **2026-08-06 PR #2 合并审计**：已将 `zhangjun221/afi-platform#2` 的代码纳入本整合分支。纳入 EWMobilitySpace、RelationshipSpace、Concordia adapter、pydantic 场景校验、eval L1/L2/L3、群体行为/因果/NLG 审计；补充可选场景 builder，并与 B1 工具目录、PIC-001、Blog/Billboard/Community 领域实现完成本地整合。当前全量离线测试为 121 passed。真实 Concordia、真实地图、模型/API 验证仍未启动；PIC-001 与 `ew_full.yaml` 不默认启用 Mobility/Relationship，避免把 opt-in replay 误报为默认场景真算。

---

## 〇、一句话

afi-platform **平台闭环已 100% 跑通**（A1–A4），B1 已完成 EW 公开工具目录 113/113 的名称、唯一实现者和路由覆盖。当前 45 个公开工具由专用环境负责，68 个由 `EWToolSpace` 承载（其中 62 个本地通用工具已具备第一轮领域状态路径、6 个仍在 provider boundary）；BlogSpace、BillboardSpace 与 CommunitySpace 已形成首批内容/公开表达/社区领域包，AWI M6 已可读取 Billboard 公开表达。PR #2 的 Mobility/Relationship、Eval、Concordia 能力已合入，但前两者仅作为 opt-in 环境，默认 PIC-001/ew_full 不启用。能跑长时程多 agent 社会→trace/replay→检测器→AWI 9族→报告。剩余差距包括 62 个工具的逐工具精确语义验收与跨域传播链、真实地图/关系 trace、外部 provider、模型验证、全量跑、统计 power 和检测器校准。

---

## 一、项目目标 + 定位

**研究命题**：长时程、弱约束多 agent 社会模拟中的 agent 安全性——风险是 trajectory-level、长出来、结构性跨阈级联的，单 agent 短程 benchmark 看不到。

**工程定位**：在 AgentSociety(AS) 引擎之上，缝合 EW（社会设定）+ AFI（审计思路），建 **audit-first** 的长时程多 agent 社会安全审计平台。**不重造 sim 引擎**，AS 作后端，审计层后端无关只读 run_dir。

**三层架构**：world（EW 翻译）/ audit（审计，后端无关）/ backend（AS 适配）。

---

## 二、路线规划（A1-A4，原计划）

来自 `architecture-and-roadmap.md` §六：

| 阶段 | 原计划交付 |
|---|---|
| **A1 起步** | pyproject(dep agentsociety2)+包结构；搬封存线 12 审计模块→`afi/audit/`；搬 backend_patches（message_log custom env）；验证 `python -m afi.audit <AS run>` 出报告 |
| **A2 EW子集翻译** | constitution/economy/landmarks/profiles → AS env/skills/agent_specs；一个 EW 式场景 YAML（5 agent 短跑）；验证"AFI on AS"成立 |
| **A3 审计+AWI** | awi.py 从 AS replay 重算 AWI；端口 AFI runtime_monitor（rolling 风险统计）；端口 scenario_designer（场景预置）；验证 AWI+audit 报告+runtime 监控 |
| **A4 完整+长时程** | 扩 EW 工具/地标翻译更全；15 天×多模型对照（对标 EW Season1 5 世界）；scenario DSL 完整；差分 vs EW Season1 ground-truth |

---

## 三、实际完成（A1-A4 逐阶段）

### 3.1 A1 骨架+资产搬迁 ✅
- `afi/` 包 + `pyproject.toml`（dep agentsociety2）
- 封存线审计模块搬入 `afi/audit/`（load/sensorium/tunnel_vision/causal/collude/decision_trace/replay_data/html_report/map_*），改 import
- `afi/backend/agentsociety.py` 适配器（subprocess 调 AS CLI，model 覆盖，WORKSPACE_PATH 注入 custom env）
- `backend_patches/simple_social_space_patched.py`：message_log 补丁迁成 custom env（reinstall-safe，不再改 AS 安装包）

### 3.2 A2 EW 设定子集翻译 ✅
- `scenarios/ew-subset.yaml`：constitution+social+economy+landmarks，5 agent
- `world/`：constitution（manifesto/constitution/governance rules）、economy、landmarks、profiles（EW agent_specs）、scenario（lite DSL）、scenario_presets
- 5 custom env：GovernanceSpace / EconomySpace / SimpleSocialSpaceAuditable / LandmarkSpace（+ A4 的 EnergySpace/CrimeSpace）
- 验证：首个 trace+replay+审计报告产出，"AFI on AS"成立

### 3.3 A3 AWI+runtime 监控+场景预置 ✅
- `audit/awi.py`：AWI **9 族**（非 11）从 AS run_dir 重算；`compute_awi_timeline` per-step；`_gini` 搬 AFI 已验证实现（2·n²·mean）
- `audit/runtime_monitor.py`：端口 AFI 思路（非代码），4 类告警（sensorium_collapse / governance_stagnation / economic_hoarding / tunnel_vision_escalation）+ `_detect_change_point`
- `world/scenario_presets.py`：3 预置（cooperative/competitive/adversarial）
- 修根因 bug：`_resolve_tick` 走完整 parent 链读 `step.count`（步序号），不再误读 `agent.tick`（3600 步长常量）——M4 per-step 真按步对齐
- `cli.py` 加 `awi` 子命令 + `run-ew --preset`

### 3.4 A4 长时程多模型+M1/M2 真算+对标 EW ✅
- `custom/envs/energy_space.py`：EnergySpace——energy 每 step 扣耗、≤0 死亡+death_log+治理处决 → **M1 真算**（从 stub 升级）
- `custom/envs/crime_space.py`：CrimeSpace——append-only crime_log.jsonl → **M2 真算**（从 0 升级）
- `awi.py::_m1_population/_m2_crime`：读 energy_agent_state / crime_log；feasibility stub→computed
- `world/scenario.py::_env_builders`：envs 可配置（默认 4 保 baseline，ew_full 加 energy/crime）
- `world/multi_model.py`：同场景×N 模型跑→跨模型 AWI 表
- `audit/statistical.py`：mean/std/CI95 + 跨模型显著性（标"非正式"）
- `audit/comparison.py`：9族×runs 对照 + M1-vs-EW 定性 bucket
- `cli.py` 加 `multi-run` 子命令 + 跨模型 HTML
- 3 模型（qwen-plus/max/turbo）× 15 sim-天实测

### 3.5 完成度总表

| 维度 | 预期（路线目标） | 已完成 | 完成度 |
|---|---|---|---|
| **平台闭环** | 跑长时程→监控→AWI→跨模型→对标 | A1→A2→A3→A4 全通 | ✅ 100% |
| **AWI 9 族** | 9 族全真实可算 | M1/M2/M4/M5/M8/M9 默认真算（6）；M6 Billboard 可算；M3/M7 在 opt-in replay 存在时可算 | 默认 6 真 + M6 已接；M3/M7 场景化待验证 |
| **EW 设定翻译** | 宪法/地标/工具/经济/治理 | EW 当前公开目录 113/113；专用环境 + EWToolSpace | 目录/路由完整；逐工具领域验收进行中 |
| **长时程** | 15 天 × 10 agent | 15 sim-天（1步/天**压缩**版）× 5 agent × 3 模型 | 压缩版 |
| **多模型** | 5 世界对照 | 3 百炼模型（qwen-plus/max/turbo） | 3/5 |
| **对标 EW** | M1-M9 全对 Season1 | 仅 M1 有 EW baseline（定性 bucket）；M2-M9 自对照 | M1 对标 + 余自对照 |
| **统计** | 多 run 置信区间 | mean/std/CI95（n=1/模型，标"非正式"） | 趋势性 |
| **scenario DSL** | 完整 pydantic + Label/ground-truth | pydantic v2 延迟校验与 eval label/scoring 已合并 | 离线代码完成，真实评测待模型 |

---

## 四、平台已建成什么

### 4.1 代码层
- **审计层**（`afi/audit/`，后端无关）：load / sensorium / tunnel_vision / causal / collude / decision_trace / replay_data / awi / runtime_monitor / statistical / comparison / html_report / map_*（可选）
- **世界层**（`afi/world/`）：scenario / scenario_presets / constitution / economy / landmarks / profiles / multi_model
- **后端**（`afi/backend/`）：agentsociety 适配器 + base ABC + backend_patches
- **CLI**（`afi/cli.py`）：audit / run-as / run-ew / awi / multi-run 五子命令
- **custom envs**（13）：GovernanceSpace / EconomySpace / SimpleSocialSpaceAuditable / LandmarkSpace / EnergySpace / CrimeSpace / BlogSpace / BillboardSpace / CommunitySpace / EWToolSpace / PlanningSpace / EWMobilitySpace / RelationshipSpace

### 4.2 实证发现（A4 已落地证据）
1. **M4 跨模型强模型-强探索**：qwen-turbo/plus/max = 3.0/4.2/5.6（avg 工具/agent），镜像 EW 模型谱（Claude/Gemini 强 vs Grok/GPT5Mini 弱）。stats M4=4.27±1.30 CI[2.76,5.77]。
2. **M1 qwen 族全崩溃**：3 模型全死（1/5、0/5、0/5），根因 agent 收 10 次"ENERGY CRITICALLY LOW—recharge"警告仍不调 recharge。≈ EW Grok/GPT5Mini collapse，非 Claude/Gemini 维持。
3. **M2=2 crimes**（multi-run 种子落地，theft+intimidation by Blackbox agent3）——M2 真 computed 非零。
4. M8 Gini=0（5 agent 信用均等无交易）/ M9 v1 passed0（投票没凑够 4/5）——诚实，本轮未涌现经济分化/修宪。

### 4.3 文档层
`architecture-and-roadmap`（路线）/ `technical-architecture`（§12 完成度）/ `three-platforms-intro`（EW/AFI/AS）/ `ew-afi-analysis` / `a2-a4-plan`（逐阶段 plan）

---

## 五、还没完成 / 缺口

### 5.1 平台保真度缺口（不阻塞研究产出，按需）
| 项 | 为什么差 | 影响 | 难度 |
|---|---|---|---|
| **MobilitySpace 地图（M3 真）** | PR #2 已提供轻量地标 recorder；真实 map.pb 仍需依赖和数据 | EWMobilitySpace 已可 opt-in，默认 PIC/ew_full 不启用，真实 Agent trace 未验收 | 高（依赖+数据） |
| **关系模型（M7 真）** | PR #2 已提供 typed RelationshipSpace 和 AWI reader | 已可 opt-in 并读取 replay；默认场景未启用，真实自主关系 trace 未验收 | 中 |
| **Billboard/Blog 接入 M6** | BillboardSpace 已有独立状态/replay/event log | M6 已优先读取 Billboard；Blog↔Billboard 跨域引用和真实 trace 仍待补 | 中 |
| **EW 工具目录** | 公开目录 113 个唯一工具 | 目录/唯一实现者/路由/M4 已验收；45 个公开工具专用化、62 个本地通用工具已具备第一轮领域状态路径并通过通用契约测试，6 个外部工具停在 provider boundary，逐工具语义仍待升级 | 🟡 |
| **10 agent × 360 tick × 5 全量** | 成本不可行（~A2×250） | 长时程是压缩版 | 高（成本） |
| **完整 pydantic scenario DSL** | A2 lite loader 够用 | pydantic v2 延迟校验已合并，仍需扩充 env/tool 级 schema | 低 |
| **Concordia 后端** | strategy 规划可换后端 | 后端可换目前是 claim 非事实 | 中 |

### 5.2 检测器校准缺口（测试套件，缓做）
- 平台建了仪器没建考卷：现有 run 无 ground-truth label → 算不了 precision/recall/latency/比基线强多少。
- 目标+plan 已写（`eval-suite-goals.md`/`eval-suite-plan.md`），代码缓做（用户决定先做旗舰，与归因 label-free 不冲突）。
- 现状能说"看到现象"，不能说"检测器准不准/多早/比现有强多少"。

### 5.3 统计 / 涌现缺口
- **统计显著性**：n=1/模型，CI 宽，仅趋势性（formal 要 30+ run，需多 seed）。
- **crime/energy 自发涌现**：LLM agent 不稳定调变异工具（recharge/crime/propose/vote），靠 intervene 种子才触发，非纯涌现。
- **intervene helper flaky**：crime/recharge 单 run 常被 drop（12 调用超 AgentSocietyHelper 预算），缩到 8 调用+前置才稳定。

### 5.4 论文/开源产出
- 路线图 M4 出成果阶段，尚未进入论文写作。

---

## 六、当前能支撑到哪（诚实边界）

✅ **能做**：
- 跑任意 EW 形状场景（YAML：任意 agent/env/种子）→ 全审计报告（AWI 9族+检测器+runtime+因果）
- 跨模型对照同一场景
- 出安全相关发现（已实证：M4 模型谱、M1 全崩溃）
- 定性对标 EW Season1 M1（qwen 族 collapse ≈ Grok/GPT5Mini）

⚠️ **能说但不能说死**：
- AWI 6 族真算但 3 族（M3/M6/M7）是代理，不能当真值
- 跨模型差异是"趋势性非正式统计"（n=1/模型，CI 宽）
- "死亡"对指标+工具门控真实，对"进程停止"是近似（AS 不杀 agent 进程）

❌ **现在说不了**：
- "检测器准不准/多早/比基线强多少"（要测试套件 label 精标）
- "全量复现 EW"（地图没接、实时外部 provider 未配置、10×360×5 没全跑）
- 正式统计显著性（要 30+ run）

**一句话定位**：平台已能支撑"跑场景→监控→量化→跨模型→出发现"的完整研究闭环；只是还不能给"检测器准度"打分（测试套件缓做）+ 保真度未到全量 EW。

---

## 七、下一步候选（平台维度，待定）

1. **测试套件 L1/L2**：补 detection 校准（label+scoring），给"检测器准不准"打分——平台"考卷"缺口。
2. **EW 保真**：地图（M3真）/ 外部 provider / 关系(M7真) / 表达(M6真)——按需，非安全驱动。
3. **多 seed + 跨模型扩**：n>1 做 formal 统计；非 qwen 模型看 collapse mode 是否不同。
4. **完整 pydantic DSL**：场景校验补强（低成本）。
5. **Concordia 后端实测**：兑现"后端可换"claim。
6. **论文写作**：平台 + A4 实证发现打包。

---

## 八、关键决策记录

| 决策 | 依据 |
|---|---|
| AS pip 依赖 + 兼容层（非 vendor 源码） | 干净切割，不背 2.7G vendor |
| 封存线审计模块搬来作基底（非重做） | 12 模块纯 stdlib 后端无关，可直接用 |
| EW 工具不一次性全翻，先子集跑通 | 内容工程非平台核心，够验证闭环 |
| 不重造 sim 引擎，借思路不搬代码 | GUARDIAN/Colosseum/AFI 一律借 idea，原生吃 AS trace |
| 不重构 CommonRun | 检测器直接读 run_dir，省工作量早交付 |
| 测试套件缓做 | label 脆弱（count/horizon 变就漂）；先做旗舰方法（归因 label-free 不冲突） |

---

## 九、一句话总结

afi-platform **平台闭环 100% 跑通**（A1-A4），B1 已覆盖公开工具目录与路由 113/113，当前 45 个公开工具专用化、68 个由 EWToolSpace 承载（62 generic + 6 provider boundary）；契约层已能区分真实 typed signature 与兼容 envelope，62 个 generic 已补第一轮领域状态路径，并把 PIC-001 的 artifact/reference 贯穿到 Community 状态和审计。AWI M6 已优先读取 Billboard 公开表达，PR #2 的 Mobility/Relationship/Eval/Concordia 代码已合入但仍有 opt-in 或外部依赖边界。剩余差距是 62 个通用工具的逐工具精确语义与跨域传播链、真实地图/关系 trace、外部 provider、模型验证、全量跑、统计 power 和检测器校准。
