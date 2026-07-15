# Contributing to afi-platform

> 给协作者：平台 A1-A4 闭环已跑通（见 `docs/progress-summary.md`），但还有一批"做更深/更全/更准"的缺口。本文列出**还没做的**、每项**怎么做**、**注意事项**。
> 领任务前先读 `README.md`（Setup）+ `docs/progress-summary.md`（完成度）+ `docs/technical-architecture.md` §12（完成度细节）+ `docs/collaboration-guide.md`（PR/review/分支/冲突流程，新人必读）。

---

## 一、怎么领任务

1. 在 GitHub Issues 里开/认领一个任务（每项 backlog 建议一个 issue）。
2. fork → `git checkout -b feat/<item>` → 改 → 提 PR。
3. PR 描述里写：改了什么、怎么验收的（跑了哪个命令、输出截图/数字）。
4. **诚实原则**：没做完的标 WIP；测不通的别假装通；依赖外部数据/模型的诚实标"未实测"。

---

## 二、Backlog：还没做的（按难度/优先级）

### B1. EW 工具补全（120+ 工具，目前只翻小子集）— 难度高·量大·非核心
- **进度（2026-07-15）**：经济类第一批已完成：支付/偷窃、Victory Arch 提案周期、Central Bank 存贷共 10 个 EW 命名工具；均接入 `EconomySpace`，保留原 AS 兼容接口。其余类别仍按批次推进，B1 整体未完成。
- **缺什么**：EW 有 120+ 工具 / ~19 类（`tools/` 目录 README + 各类）。afi 现在只翻译了支撑 ew-subset/ew_full 跑通的小子集（observe/recharge/commit_crime/propose/vote/execute_skill_script/send_message 等）。
- **为什么没做**：纯内容工程，非平台核心；够验证闭环。
- **怎么做**：参考 EW 源（`docs/ew-afi-analysis.md` 有 EW 工具清单）→ 在 `afi/world/` 加 skill/tool 定义 → 接进 AS agent 的 codegen_router。**不要一次性全翻**，按类分批（如先"经济类"、再"社交类"）。
- **验收**：新工具能被 agent 调用（trace 出现 `react.action`）；该工具在 M4 工具多样性里被计入。
- **注意**：工具名/语义要贴 EW 原文，别自创；EW 是研究用 license，别直接搬代码，按设定重写。

### B2. MobilitySpace 地图（M3 从代理升真算）— 难度高·依赖重
- **缺什么**：M3 现在是代理（landmark 查询计数，非真移动）。`afi/audit/map_places.py`+`map_bg.py` 已写好但**没数据没依赖**跑不了。
- **为什么没做**：需 `pyproj`+`pycityproto`+城市 `.pb` map 数据（依赖重 + 数据大，不入 git）。
- **怎么做**：`pip install -e ".[map]"` 装可选依赖；按 AS 的 MobilitySpace 文档准备 `.pb` 城市数据（OSM 抽取）；场景 YAML 加 `MobilitySpace` 到 envs；验证 `map_places.py` 出地标坐标 + agent 轨迹。
- **验收**：M3 feasibility 从 `proxy` 升 `computed`；HTML 报告里位置轨迹块有真实坐标。
- **注意**：`.pb` 数据**别提交**（加 .gitignore）；mac 零 GPU 也能跑（AS 设计如此）；`replay_data.py:141` 已有 MobilitySpace replay 读取代码可复用。

### B3. RelationshipSpace（M7 从代理升真算）— 中等
- **缺什么**：M7 现在只算消息图密度（无向边），没关系类型。EW 有 ally/rival/mentor 等关系类型。
- **怎么做**：新建 `custom/envs/relationship_space.py`（仿 governance_space.py 模式：EnvBase 子类 + state JSON + 工具 expose）；定义关系类型枚举 + add/query 关系工具；AWI `_m7_social` 改读 relationship_env_state。
- **验收**：M7 feasibility `proxy→computed`；agent 能建立/查询关系；AWI 报关系类型分布。
- **注意**：关系是 agent 间结构，要 append-only + per-step replay 快照（照 energy_space 的 `energy_agent_state` 模式）。

### B4. Billboard/Blog 公开表达（M6 从代理升真算）— 中等
- **缺什么**：M6 现在用 `send_message` 量代理（私信非公开表达）。EW 的公开表达是独立工具（Billboard 广告牌 / Blog）。
- **怎么做**：新建 `custom/envs/billboard_space.py`（公开 append-only 留言板）；expose post_to_billboard/read_billboard 工具；AWI `_m6` 改读 billboard_log。
- **验收**：M6 `proxy→computed`；公开 vs 私信区分开。
- **注意**：现在 `landmark_space.py` 里有个"Agent Billboard"文本地标（不是真工具）——别混淆，那是设定地标不是表达工具。

### B5. 完整 pydantic scenario DSL — 低难度
- **缺什么**：`afi/world/scenario.py::load_scenario` 现在只是 `yaml.safe_load`（无 schema 校验）。场景写错（env 名拼错/缺字段）跑到 AS 才报错。
- **怎么做**：加 `pydantic` 模型（Scenario/Agent/Env/World/Step），load_scenario 改 `Scenario.model_validate`；optional dep `pydantic` 进 pyproject `[yaml]` extra 或单独 extra。
- **验收**：故意写错的场景 YAML 在 load 时就报清晰错（不用等 AS 跑）。
- **注意**：保持向后兼容（现有 ew-subset/ew_full.yaml 要还能 load）；pydantic 是 optional（别让它成核心依赖）。

### B6. Concordia 后端适配器 — 中等·兑现"后端可换"claim
- **缺什么**：`afi/backend/base.py` 有 `BackendAdapter` ABC，只有 `agentsociety.py` 一个实现。`base.py` 注释提过"a future Concordia adapter would live in concordia.py"——没实现。
- **怎么做**：新建 `afi/backend/concordia.py`，实现 `BackendAdapter`（scenario→Concordia 格式→跑→run_dir）；CLI 加 `--backend concordia` 选项。
- **验收**：同一场景 YAML 能在 AS 和 Concordia 两个后端跑（audit 层不变，证明后端无关）。
- **注意**：审计层（`afi/audit/`）必须保持后端无关（只读 run_dir，不 import 后端）——这是核心架构不变量，别破坏。

### B7. 测试套件（缓做，但也是缺口）— 中等
- **缺什么**：平台建了仪器没建考卷——无 ground-truth label → 说不了"检测器准不准/多早/比基线强多少"。
- **现状**：`docs/eval-suite-goals.md`+`eval-suite-plan.md` 已写目标+plan；`tests/` 空目录。
- **怎么做**：按 `eval-suite-plan.md` 三层（L1 精标核心 / L2 参数化扩展 / L3 任意YAML）实现 `eval/` 子包；先 L1（6 注入场景+label+scoring）。
- **验收**：`python -m eval run-one <场景>` 出一行 `{precision,recall,latency,severity_mae,vs_naive}`。
- **注意**：label 脆弱（count/horizon 变就漂）——固定 count+horizon 是 feature 不是 bug（benchmark 该死）；verifier 逻辑 ≠ 检测器逻辑（防循环自证，见 `docs/eval-suite-plan.md`）。

### B8. 多 seed + 跨模型扩展（统计 power）— 中等·成本
- **缺什么**：A4 只 n=1/模型（qwen-plus/max/turbo），CI 宽，仅趋势性。formal 显著性要 30+ run。
- **怎么做**：扩 `multi_model.py` 支持 multi-seed；跑 6 模板×3 agent数×3 模型×3 seed ≈ 160 run（见 `eval-suite-plan.md` L2）。
- **验收**：per-model recall/precision 带 CI95；跨模型差异能标"显著/趋势"。
- **注意**：成本（每 run 几分钟+API token）；先跑子集验证 pipeline 再全量；非 qwen 模型（Claude/GPT 系）需对应 API key。

### B9. `tests/` 填充（单元测试）— 低难度·高价值
- **缺什么**：`tests/` 空目录。核心模块（`awi._gini`、`causal._resolve_tick`、`attribution.localize_first_domino`、`scenario.build_init_config`）没单测。
- **怎么做**：用 pytest（已在 `[dev]` extra）写：Gini 边界（等分→0/独占→(n-1)/n）、_resolve_tick 读 step.count 不读 agent.tick=3600、localize 命中 missed_recharge、scenario load+build。
- **验收**：`pytest tests/` 全绿。
- **注意**：单测用现有 run 数据（`runs/ew_multi/` 本地有，但 .gitignore 排了——测试 fixture 要自带小样本或 skip 无数据时）。

### B10. 论文/文档 — 持续
- **缺什么**：路线图 M4 出成果阶段，未进入论文写作。
- **怎么做**：把 platform + A4 实证发现（M4 模型谱、M1 全崩溃）+ phase1 旗舰（第一骨牌归因+反事实，见 `docs/phase1-first-domino/`）打包成论文草稿。
- **注意**：novelty 措辞用 `docs/phase1-first-domino/society-alignment-evidence.md` 的收窄版（**别退回"field 无人 formalize"**——已被证伪，6 篇相邻工作在那里）。

---

## 三、环境/协作注意事项

### AS 后端（双模式）
- 只读命令（`audit`/`awi`/`attribution` 无 `--counterfactual`）**不调 AS**，clone 后 `pip install -e .[yaml]` 就能跑。
- 跑模拟（`run-ew`/`multi-run`/`attribution --counterfactual`）需 AS 后端：`pip install agentsociety2`（pip 模式）或 `export AS_HOME=<AS checkout>`（checkout 模式，见 README）。
- API key 放项目根 `.env`（pip 模式）或 `$AS_HOME/.env`（checkout 模式）——**.env 已被 .gitignore，别提交密钥**。

### 不要提交的东西（.gitignore 已覆盖，自觉遵守）
- `runs/`（run 产物，含 trace/replay，大）、`afi_report_*.html`（生成的大 HTML）、`agentsociety_data/`（codegen cache）、`results/`（生成的 JSON）、`__pycache__/`、`.env`、`*.pkl`。
- 要看一个 run 长啥样，本地跑 `python -m afi.cli run-ew scenarios/ew_full.yaml --run-dir runs/x --audit` 生成。

### 代码约定（沿用仓库 AGENTS.md/CLAUDE.md）
- **审计层后端无关**：`afi/audit/` 只读 run_dir，不 import 后端、不调 AS API。这是核心不变量，别破坏。
- **借思路不搬代码**：GUARDIAN/Colosseum/AFI/EW 一律借指标定义/rubric/idea，代码不直接 import（license + 耦合原因）。
- **诚实声明**：代理指标标 `[proxy]`、stub 标 `[stub]`、未实测标"未核实"；别把演示 run 当全量复现。
- **语言**：研究文档/报告中文，代码 docstring/help 英文注释（匹配文件已有风格）。
- **最小 diff + 改根因**：修 bug 改根因不打补丁；验证跑真实命令（`python -m afi.cli ...` 出报告才算通）。

---

## 四、一图流：现在到哪 + 缺口在哪

```
平台闭环 ✅ 100%（A1-A4）
  ├ AWI 9 族：6 真算 ✅ | 3 代理 ⏳(B2 M3 / B3 M7 / B4 M6)
  ├ EW 设定：子集 ✅ | 120+工具 ⏳(B1) | 地图 ⏳(B2)
  ├ 长时程：压缩版 ✅ | 全量 ⏳(B8 成本)
  ├ 多模型：3/5 ✅ | 统计power ⏳(B8)
  ├ 后端：AS ✅ | Concordia ⏳(B6)
  ├ DSL：lite ✅ | pydantic ⏳(B5)
  ├ 测试：⏳(B7 label套件 + B9 单测)
  └ 论文：⏳(B10)
```

挑一个 `⏳` 开干。建议入门顺序：**B9（单测，最低门槛）→ B5（pydantic DSL）→ B3/B4（M7/M6 真算，中等）→ B6（Concordia）→ B1/B2（工具/地图，量大）**。
