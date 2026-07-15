# afi-platform

> 长时程、弱约束多 agent 社会模拟中的 agent 安全审计平台。
> 在 AgentSociety(AS) 引擎之上，缝合 Emergence World(EW) 社会设定 + ai-freedom-island(AFI) 审计思路，audit-first，不重造 sim 引擎。

## 这是什么

研究命题：**长时程多 agent 社会里的安全风险是 trajectory-level、长出来、结构性跨阈级联的**——单 agent 短程 benchmark 看不到。

afi-platform 把三件事缝合成一个可跑的平台：
- **AS**（AgentSociety 2）作模拟引擎（Ray + OTel trace + replay + 16 env 模块，零 GPU）。
- **EW**（Emergence World）作社会设定翻译（manifesto/宪法/治理/经济/地标/profiles → AS env+skills+agents）。
- **AFI** 审计思路（sensorium/tunnel-vision/因果链/AWI 9 族）端口到 AS trace 上。

三层架构：`world/`（EW 翻译）/ `audit/`（审计，后端无关，只读 run_dir）/ `backend/`（AS 适配）。

完成度见 `docs/progress-summary.md` 与 `docs/technical-architecture.md` §12。

## 仓库结构

```
afi-platform/
  afi/
    audit/      # 后端无关审计：load/sensorium/tunnel_vision/causal(+event_graph)/
                #   collude/decision_trace/replay_data/awi(9族)/runtime_monitor/
                #   statistical/comparison/html_report/attribution(第一骨牌归因)
    world/      # EW 翻译：scenario(DSL)/scenario_presets/constitution/economy/
                #   landmarks/profiles/multi_model/counterfactual(反事实rerun)
    backend/    # AS 适配器（双模式）+ base ABC + backend_patches(message_log)
    cli.py      # audit/run-as/run-ew/awi/multi-run/attribution 子命令
  custom/envs/  # AS 热加载 custom env：GovernanceSpace/EconomySpace/
                #   SimpleSocialSpaceAuditable/LandmarkSpace/EnergySpace(M1死亡)/CrimeSpace(M2犯罪)
  scenarios/    # EW 场景 YAML：ew-subset.yaml / ew_full.yaml(15天)
  demo/         # Gradio 8-tab 演示（app.py + styles.py）
  docs/         # 架构/路线/完成度/各阶段 plan/测试套件/phase1 旗舰
  tests/        # （待填）
  pyproject.toml
```

## Setup（协作者）

### 1. clone + venv + 装 afi
```bash
git clone <this-repo> afi-platform && cd afi-platform
python -m venv .venv && source .venv/bin/activate
pip install -e ".[yaml]"
```

### 2. 装 AS 后端（二选一）

**模式 A — pip（最简）**：在同一个 venv 装 AS 引擎
```bash
pip install agentsociety2
```

**模式 B — AS checkout（完整，推荐用 AS 源码调试的人）**：
```bash
git clone https://github.com/tsinghua-fib-lab/AgentSociety.git /path/to/AgentSociety
cd /path/to/AgentSociety && python -m venv .venv && source .venv/bin/activate
pip install -e .   # 装 AS + 其依赖
export AS_HOME=/path/to/AgentSociety   # 指向 checkout（含 .venv + .env）
```

适配器见 `--as-home` 或 `AS_HOME` 环境变量。**没设 AS_HOME → 走 pip 模式**（用当前 venv 的 python 跑 `agentsociety2.society.cli`）。

### 3. API key（百炼/DashScope）
在项目根放 `.env`（已被 .gitignore，不会上传）：
```
DASHSCOPE_API_KEY=sk-...
# 或 AS 期望的 LLM 环境变量
```
- 模式 B：`.env` 放 `AS_HOME` 目录；模式 A：放项目根。

### 4. 跑
```bash
# 跑 EW 场景 → AS run → 审计
python -m afi.cli run-ew scenarios/ew_full.yaml --run-dir runs/myrun --model qwen-plus --audit

# 多模型对照
python -m afi.cli multi-run scenarios/ew_full.yaml --models qwen-plus,qwen-max,qwen-turbo --run-root runs/ew_multi
```

## 用法

```bash
# 审计一个/多个 run（多 run → 跨模型 AWI 对照 HTML）
python -m afi.cli audit <run1> [<run2> ...] [--out html]

# AWI 9 族 + runtime 告警
python -m afi.cli awi <run_dir> [--json report.json] [--no-runtime]

# 第一骨牌归因（label-free，读 run_dir）+ 可选反事实 rerun
python -m afi.cli attribution <run_dir> --outcome m1_collapse
python -m afi.cli attribution <run_dir> --counterfactual \
    --scenario scenarios/ew_full.yaml --model qwen-plus --cf-run-dir runs/x_cf

# 只读命令（audit/awi/attribution 无 --counterfactual）不调 AS，不需要 AS_HOME
```

> 注：`python -m afi` 若报"cannot be directly executed"，用 `python -m afi.cli`（包无 `__main__.py`），或装后用 console script `run-afi`。

## 完成度（诚实）

- ✅ **平台闭环 100%**（A1 骨架→A2 EW子集→A3 AWI+监控→A4 长时程多模型+M1/M2 真算+对标EW）
- AWI 9 族：6 真算（M1/M2/M4/M5/M8/M9）+ 3 代理（M3 地图/M6 公开表达/M7 关系类型）
- 实测发现：M4 跨模型强模型-强探索（3.0/4.2/5.6 镜像 EW 模型谱）；M1 qwen 族全崩溃（neglect recharge）
- **A4 ≠ 全量 EW Season1 复现**（EW 仅发 M1 baseline；全量 10×360×5 成本不可行；MobilitySpace 地图依赖重）

差的都在"做更深/更全/更准"，不在"闭环没通"——详见 `docs/progress-summary.md`。

## 文档

- `docs/progress-summary.md` — 平台搭建进展总结（规划 vs 实际）
- `docs/collaboration-guide.md` — **协作开发指南（给项目管理者+协作者，含 PR/review/冲突/分支保护）**
- `docs/technical-architecture.md` — 技术架构 + §12 完成度
- `docs/architecture-and-roadmap.md` — 形态/架构/A1-A4 路线
- `docs/three-platforms-intro.md` — EW/AFI/AS 三平台
- `docs/phase1-first-domino/` — 第一骨牌归因 + 反事实世界分叉旗舰（pilot + 理论 + novelty 核验）
- `docs/eval-suite-goals.md` + `docs/eval-suite-plan.md` — 测试套件（缓做）目标+实现 plan
- `DEVLOG.md` — 轮次建设日志

## 上游

- **AgentSociety 2** — `https://github.com/tsinghua-fib-lab/AgentSociety`（sim 引擎，pip dep `agentsociety2`）
- **Emergence World** — 官方世界设定集（manifesto/宪法/地标/AWI/Season1 数据，研究用 license）
- **ai-freedom-island (AFI)** — EW 可运行复现 + 审计扩展（audit.py + AWI + crime_log）

B1 工具扩展已覆盖 EW 当前公开目录的 113/113 个唯一工具。经济、治理、能量、
消息、犯罪和地标由专用环境负责，其余 101 个由可扩展 `EWToolSpace` 注册；实时
外部能力通过 provider 请求接口接入。工具按 EW 公开语义重写，未复制上游代码。

## License

CC BY-NC 4.0（见 `pyproject.toml`）。
