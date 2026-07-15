# afi-platform 平台搭建进展总结（规划 vs 实际）

> 2026-07-14。聚焦**平台搭建（A1-A4）**的进展总结：规划做什么、实际做到哪、还差什么。
> 数据来自代码与文档实测（`architecture-and-roadmap.md` 路线、`technical-architecture.md` §12 完成度、`afi/` 模块、`custom/envs/`、`runs/` 均核实），非凭记忆。
> 范围限定平台本身；旗舰方法（第一骨牌归因/反事实）不在此文。

---

## 〇、一句话

afi-platform **平台闭环已 100% 跑通**（A1–A4），B1 又完成 EW 公开工具目录 113/113。能跑长时程多 agent 社会→trace/replay→检测器→AWI 9族→报告。剩余差距在地图、关系/表达指标、外部 provider、全量跑、统计 power 和检测器校准。

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
| **AWI 9 族** | 9 族全真实可算 | M1/M2/M4/M5/M8/M9 真算（6）；M3/M6/M7 代理（3） | 6/9 真 + 3 代理 |
| **EW 设定翻译** | 宪法/地标/工具/经济/治理 | EW 当前公开目录 113/113；专用环境 + EWToolSpace | 公开工具完整 |
| **长时程** | 15 天 × 10 agent | 15 sim-天（1步/天**压缩**版）× 5 agent × 3 模型 | 压缩版 |
| **多模型** | 5 世界对照 | 3 百炼模型（qwen-plus/max/turbo） | 3/5 |
| **对标 EW** | M1-M9 全对 Season1 | 仅 M1 有 EW baseline（定性 bucket）；M2-M9 自对照 | M1 对标 + 余自对照 |
| **统计** | 多 run 置信区间 | mean/std/CI95（n=1/模型，标"非正式"） | 趋势性 |
| **scenario DSL** | 完整 pydantic + Label/ground-truth | lite loader（够跑）；Label/ground-truth（测试套件）缓做 | 部分 |

---

## 四、平台已建成什么

### 4.1 代码层
- **审计层**（`afi/audit/`，后端无关）：load / sensorium / tunnel_vision / causal / collude / decision_trace / replay_data / awi / runtime_monitor / statistical / comparison / html_report / map_*（可选）
- **世界层**（`afi/world/`）：scenario / scenario_presets / constitution / economy / landmarks / profiles / multi_model
- **后端**（`afi/backend/`）：agentsociety 适配器 + base ABC + backend_patches
- **CLI**（`afi/cli.py`）：audit / run-as / run-ew / awi / multi-run 五子命令
- **custom envs**（6）：GovernanceSpace / EconomySpace / SimpleSocialSpaceAuditable / LandmarkSpace / EnergySpace / CrimeSpace

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
| **MobilitySpace 地图（M3 真）** | 需 pyproj+pycityproto+城市 map.pb | M3 仍代理（地标可点名不可走动） | 高（依赖+数据） |
| **关系模型（M7 真）** | EW 有 ally/rival/mentor，需 RelationshipSpace | M7 只能算网络密度，无关系类型 | 中 |
| **Billboard/Blog 接入 M6** | B1 已有独立工具，但 AWI 尚未读取其状态 | M6 仍用 send_message 代理 | 中 |
| **EW 工具目录** | 公开目录 113 个唯一工具 | B1 已完成注册、状态、路由和 M4 验收 | ✅ |
| **10 agent × 360 tick × 5 全量** | 成本不可行（~A2×250） | 长时程是压缩版 | 高（成本） |
| **完整 pydantic scenario DSL** | A2 lite loader 够用 | 场景校验弱 | 低 |
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

afi-platform **平台闭环 100% 跑通**（A1-A4），B1 已覆盖公开工具 113/113，AWI 6/9 真算+3 代理。剩余差距是地图、外部 provider、关系/表达真算、全量跑、统计 power 和检测器校准。
