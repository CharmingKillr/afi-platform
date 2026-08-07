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

### B1. EW 工具补全 🟡（目录与路由完成；领域语义持续补全）
- **已完成**：EW 当前公开 `tools/README.md` 共 113 个唯一名称，已 113/113 注册且在 `ew_full.yaml` 中每个名称只有一个实现者。规划类 6 个由 `PlanningSpace` 负责；Blog 内容类 6 个由 `BlogSpace` 负责；Billboard 公开表达类 6 个由 `BillboardSpace` 负责；其他专用环境负责 21 个；剩余 74 个由 `EWToolSpace` 承载（其中 68 个本地通用实现、6 个 provider boundary）。
- **边界说明**：EW 的“120+”包含演进中的历史/内部工具，公开仓库当前只能逐项核验 113 个。实时新闻、网页、论文、天气、图片生成采用 `in_progress` provider 请求接口；未配置 provider 时不伪造结果。
- **实现**：`afi/world/ew_tools.py` 固化可审计目录；`EWToolSpace` 采用声明式注册、分类门控、有界查询、同 step 幂等、Replay 快照和 resume；agent 操作说明随模块分发。
- **还需完成**：将 68 个本地通用实现按领域逐步升级为精确签名、权限、状态机、幂等、审计事件和真实 Agent 场景均已验收的专用实现；BlogSpace/BillboardSpace 仍需补真实 Agent trace 和完整跨域审核工作流。
- **验收**：覆盖测试锁定 113/113 且拒绝重复实现者；pytest 进入 CI；标准 `react.action` spans 中的新工具由 M4 正确去重计数。
- **注意**：工具名/语义要贴 EW 原文，别自创；EW 是研究用 license，别直接搬代码，按设定重写。

### B2. MobilitySpace 地图（M3 从代理升真算）— 🟡代码已合并，场景验证待补
- **已合并**：PR #2 提供 `custom/envs/ew_mobility_space.py` 和 AWI `_m3_mobility_computed()`；当前版本已将 `EWMobilitySpace` 注册为可选场景模块，相关单测纳入全量测试。
- **当前边界**：这是基于 EW 命名地标坐标的轻量 recorder，不等同于真实城市 `.pb` 地图；`ew_full.yaml` 与 PIC-001 默认不启用它，因此默认场景的 M3 仍是 proxy。
- **下一步**：如需 M3 真算，准备 `pyproj`/`pycityproto` 与城市 `.pb` 数据，或明确采用轻量地标模式，再在专门 YAML 中启用并跑真实 Agent trace。
- **注意**：`.pb` 数据**别提交**；没有真实轨迹证据时不能把 B2 标成地图验收完成。

### B3. RelationshipSpace（M7 从代理升真算）— 🟡代码已合并，场景验证待补
- **已合并**：PR #2 提供 `RelationshipSpace`、五类关系枚举、关系操作工具、state/log/replay 和 AWI typed relationship reader；当前版本已注册为可选场景模块，并把类型分布暴露到 `AWISnapshot`。
- **当前边界**：PIC-001 与 `ew_full.yaml` 默认不挂载该环境，现有证据是离线 replay fixture 和单测，不是完整 Agent 自主建立关系的 trace。
- **下一步**：在独立关系验证 YAML 中启用环境，补 form/query/dissolve 的权限、幂等和真实 Agent trace，再把 M7 从 proxy 结论升级为场景级 computed。
- **注意**：没有真实关系 replay 时，报告必须继续标记 M7 为 proxy。

### B4. Billboard/Blog 公开表达（M6 从代理升真算）— 已完成第一阶段
- **已完成**：新建 `custom/envs/billboard_space.py`（公开 append-only 事件与软删除审计）；6 个 Billboard 工具采用显式领域参数，并接入 `ew_full.yaml` 与 PIC-001。
- **已完成**：AWI `_m6` 优先读取 `billboard_env_state` / `billboard_event_log.jsonl`，没有 Billboard 数据的历史 run 仍明确降级为 send_message proxy。
- **剩余**：Blog 与 Billboard 的跨域引用链、真实 Agent trace 和多 run 指标校准仍需补充。
- **注意**：现在 `landmark_space.py` 里有个"Agent Billboard"文本地标（不是真工具）——别混淆，那是设定地标不是表达工具。

### B5. 完整 pydantic scenario DSL — ✅代码已合并
- **已完成**：`load_scenario()` 在 pydantic v2 可用时执行延迟 schema 校验；非法 step 类型会在加载阶段给出字段级 `ValueError`，无 pydantic 时保持向后兼容。
- **验收证据**：`tests/test_awi_and_envs.py` 覆盖合法场景与非法 step；全量测试通过。
- **边界**：pydantic 仍是可选能力，当前 schema 对额外场景字段保持允许，不能替代运行时的 env registry/工具契约检查。

### B6. Concordia 后端适配器 — 🟡代码已合并，真实后端待验证
- **已合并**：`afi/backend/concordia.py`、worker 和 `ConcordiaAdapter` 已纳入；适配器生成与 AS 审计层兼容的 run_dir，审计层仍不依赖具体后端。
- **当前边界**：本机没有完成真实 Concordia 安装与运行验证；worker 的 stub/兼容路径不能等同于真实 Concordia 实验。
- **下一步**：准备可用 Concordia 环境，用同一场景分别运行 AS 与 Concordia，比较 trace/replay/AWI 输出后再关闭 B6。

### B7. 测试套件 — ✅离线评测框架已合并，真实模型运行待补
- **已完成**：PR #2 纳入 L1/L2/L3 `eval/` 包、7 个标注场景、评分/verifier/grid/report/CLI，以及群体行为、因果和 NLG 相关审计模块。
- **验收证据**：PR 自带 25 个评测单测；与当前 PIC-001/B1 测试合并后，本地全量为 `115 passed`。
- **当前边界**：模型/API 不可用时不能声称完成真实跨模型评测；历史 `b8_qwen_cooperative` 结果仍需按报告边界解读。

### B8. 多 seed + 跨模型扩展（统计 power）— 中等·成本
- **缺什么**：A4 只 n=1/模型（qwen-plus/max/turbo），CI 宽，仅趋势性。formal 显著性要 30+ run。
- **已合并**：`eval/grid.py` 与 `eval/run_eval.py` 已支持 templates×models×seeds 网格及 CSV/CI95 聚合；当前仍没有新增真实模型 run。
- **怎么做**：拿到有效模型服务后跑 6 模板×3 agent数×3 模型×3 seed ≈ 160 run（见 `eval-suite-plan.md` L2）。
- **验收**：per-model recall/precision 带 CI95；跨模型差异能标"显著/趋势"。
- **注意**：成本（每 run 几分钟+API token）；先跑子集验证 pipeline 再全量；非 qwen 模型（Claude/GPT 系）需对应 API key。

### B9. `tests/` 填充 — ✅本地单测已合并
- **已完成**：PR #2 纳入 AWI、场景 DSL、环境导入、评测评分和群体行为单测；当前又补充了 registry 对新环境和 PIC-001 工具契约的覆盖。
- **验收证据**：当前工作区全量 `pytest -q` 为 `115 passed`。
- **注意**：全量通过只证明离线代码契约，不代表模型调用、真实地图、真实 Concordia 或 PIC-001 自主闭环已经通过。

### B10. 论文/文档 — 持续
- **缺什么**：路线图 M4 出成果阶段，未进入论文写作。
- **怎么做**：把 platform + A4 实证发现（M4 模型谱、M1 全崩溃）+ phase1 旗舰（第一骨牌归因+反事实，见 `docs/phase1-first-domino/`）打包成论文草稿。
- **注意**：novelty 措辞用 `docs/phase1-first-domino/society-alignment-evidence.md` 的收窄版（**别退回"field 无人 formalize"**——已被证伪，6 篇相邻工作在那里）。

---

## 三、环境/协作注意事项

### AS 后端（双模式）
- 只读命令（`audit`/`awi`/`attribution` 无 `--counterfactual`）**不调 AS**，clone 后 `pip install -e .` 就能跑；完整仿真再安装 `.[full]`。
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
  ├ AWI 9 族：6 真算 ✅ | M3/M7 需 opt-in replay，M6 已接 Billboard
  ├ EW 设定：目录/路由 113/113 ✅ | Billboard 首批领域验收 ✅，其余 68 个 generic ⏳(B1) | 地图 ⏳(B2)
  ├ 长时程：压缩版 ✅ | 全量 ⏳(B8 成本)
  ├ 多模型：3/5 ✅ | 统计power ⏳(B8)
  ├ 后端：AS ✅ | Concordia 代码合并、真实运行 ⏳(B6)
  ├ DSL：lite ✅ | pydantic 校验 ✅(可选)
  ├ 测试：离线评测/单测 ✅ | 真实模型评测 ⏳(B7/B8)
  └ 论文：⏳(B10)
```

当前最值得继续的是：**B1 通用工具领域化 → B2 真实地图/移动 trace → B3 关系场景 trace → B6 真实 Concordia → B8 多 seed/跨模型**。
