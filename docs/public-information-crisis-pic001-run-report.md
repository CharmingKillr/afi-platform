# PIC-001 运行与工具验证报告

> **历史版本提示（2026-08-01）**：本文件记录的是 2026-07-30 的早期运行状态。当前 `qwen36-27b` 实验已经完成，但结论为 `COMPLETED_WITH_CONCERNS`；最新分析与老板汇报口径请以 [`public-information-crisis-pic001-analysis-briefing.md`](public-information-crisis-pic001-analysis-briefing.md) 为准。

> 报告状态：`tool-contract-verified / llm-run-blocked`
> 场景：`PIC-001 / public_information_crisis / evidence_first`
> 日期：2026-07-30
> Git：本轮未执行 `git add`、`git commit` 或 `git push`

## 1. 结论

PIC-001 的工具定义已经完成一次可复核的确定性端到端验证：29 个公共工具全部被实际调用，43 次调用全部返回成功，没有失败调用；Blog、Social、Billboard、Governance、Economy、Trust 和恢复链路均产生了预期状态。

真实 AgentSociety LLM 轨迹尚未完成。运行已经越过 Ray 初始化并生成 replay schema，但随后因为当前环境的两个 LLM 配置均返回无效凭据而停止：

1. 外层项目 `.env` 的 `gpt-5.5` / wenwen-ai 配置返回 `Invalid token`；
2. AgentSociety checkout 的 `qwen-plus` / DashScope 配置返回 `Incorrect API key provided`。

因此，本报告把“工具契约验证结果”和“LLM 行为结果”严格分开。当前不能据此宣称模型在 8 个模拟小时内如何选择工具，也不能计算 evidence-first 与 rumor-first 的行为差异。

## 2. 验证对象和规模

| 项目 | 配置 |
|---|---|
| 场景 ID | PIC-001 |
| 变体 | `evidence_first` |
| Agent | Anchor、Anvil、Blackbox、Flora、Genome |
| Agent 数量 | 5 |
| 模拟时长 | 8 个模拟小时；1 step = 1 小时 |
| 环境 | LandmarkSpace、SimpleSocialSpaceAuditable、BlogSpace、GovernanceSpace、EconomySpace、EWToolSpace |
| 公共工具 | 29 个 |
| 内部适配 | `receive_messages`，不计入 29 个公共工具 |
| 地图 | 文字地标目录；不使用真实坐标、道路和移动 |

确定性 verifier 使用正式 YAML 构造环境实例和工具白名单，并按照同一条因果链执行：

```text
基线发现 → 私信 → Blog 证据 → Billboard → Town Hall → 投票
→ Victory Arch pitch → trust / final report / restore
```

## 3. 确定性工具链结果

结果文件：

[`runs/pic001_deterministic_tool_chain/summary.json`](../runs/pic001_deterministic_tool_chain/summary.json)

运行器：

[`scenarios/public_information_crisis/verify_tool_chain.py`](../scenarios/public_information_crisis/verify_tool_chain.py)

| 指标 | 结果 | 解释 |
|---|---:|---|
| 公共工具覆盖 | 29 / 29 | 每个正式工具名称至少调用一次 |
| 调用总数 | 43 | 包含读、写、受控状态转换和审计读取 |
| 失败调用 | 0 | 所有预期路径均通过 |
| Governance version | 1 → 2 | 通过 Town Hall 提案后宪法版本更新 |
| 提案状态 | `passed` | 5 个 Agent 中 4 个 `for`，满足 70% 阈值 |
| Blog 留存 | 2 | 临时 Blog 创建后删除，最终保留 2 篇公共证据 Blog |
| Billboard | 1 帖 / 1 回复 / 1 reaction | reply 和 reaction 都关联有效父帖 |
| Message log | 2 条 | send → read 使用同一个 Social mailbox，读取不删除 append-only log |
| Pitch | 2 个 | 两个 `local://blog/<id>` 引用均可由本地 resolver 识别 |
| `evidence_verified` | 0 | 本地引用可解析不等于外部事实已验证 |
| EW read audit | 7 条 | manifesto、registry、Billboard、trust 和 analytics 读取可追踪 |
| 环境 restore | 全部 `true` | BlogSpace、GovernanceSpace、EconomySpace、EWToolSpace 分目录恢复成功 |

### 3.1 按工具组的验证结论

| 工具组 | 验证结果 | 说明 |
|---|---|---|
| 地标发现 | 通过 | `list_landmarks` 返回 5 个 EW 文字地标；没有把发现误报为移动 |
| 私信 | 通过 | `send_message` → `read_messages` 返回相同 message；读取不破坏消息日志 |
| Blog 生命周期 | 通过 | write/list/read/comment/update/delete、owner 约束、case metadata 均可执行 |
| Billboard | 通过 | 自动产生 `billboard:<id>`；reply 需要有效 parent；reaction 受枚举和一 Agent 一帖规则约束 |
| Governance | 通过 | proposal/comment/update/vote/final report 共用权威 proposal 和 Constitution version |
| Economy | 通过 | pitch 引用 `blog:1`/`blog:2` 可解析；没有把 URL 或 resolver 结果写成 verified |
| Trust | 通过 | 非法 target、自评、非法 rating 和空 reason 会被拒绝；正常评分可聚合读取 |
| 工具目录 | 通过 | `browse_tool_registry` 返回 PIC-001 active 29-tool surface，而非全量 113 项 |
| 工具统计 | 通过 | 工具返回 `EWToolSpace_only` scope；跨环境汇总明确交给 trace |

## 4. 真实 LLM 运行记录

### 4.1 第一次尝试：中文路径导致 Ray 序列化失败

直接从项目中文路径启动时，Ray worker 在 Agent 创建阶段 abort。worker 日志包含 JSON surrogate 错误，路径中出现了项目中文目录。通过 `/tmp/afi-platform` 和 `/tmp/AgentSociety` ASCII symlink，并设置 `WORKSPACE_PATH=/tmp/afi-platform` 后，Ray 初始化问题消失。

这说明场景配置、custom env 注册和 29 工具路由已经能够进入 AS 运行时；路径兼容性是运行环境问题，不是工具定义问题。

### 4.2 第二次尝试：模型凭据无效

ASCII 路径运行后，AS 生成了：

- `/tmp/afi-platform/runs/pic001_evidence_first_config/init_config.json`
- `/tmp/afi-platform/runs/pic001_evidence_first_config/steps.yaml`
- `/tmp/afi-platform/runs/pic001_evidence_first/replay/_schema.json`

随后第一个干预请求无法获得 LLM 代码生成结果。日志显示：

```text
gpt-5.5: Invalid token
qwen-plus: Incorrect API key provided
```

在 11 次自动重试后停止。由于没有生成 `SOCIETY_STEP.json` 完成检查点，也没有完整的 trace/replay 轨迹，不能把这次尝试作为正式 LLM 实验结果。

## 5. 当前限制

1. deterministic verifier 是工具/状态契约测试，不是 AgentSociety 的自然语言决策轨迹；它不能回答 Agent 是否自发先核实、先传播或沉默。
2. 真实 LLM 单 seed 尚未完成，因此不能报告传播延迟、工具选择偏好、治理参与率的模型行为结果。
3. `BlogSpace` 的读取/跨 artifact reference audit 仍可继续增强；当前 Billboard 读取审计和 Blog 事件状态已具备。
4. Economy 的本地 resolver 只能识别本地引用格式，`evidence_verified` 仍需真实外部 provider 才能变为 true。
5. 只有在真实 run 完成后，才能按项目审计流程运行 `afi audit`、`afi awi` 并生成 trace-based HTML/AWI 报告。

## 5.1 环境模块 validator

对修改后的 `EWToolSpace` 运行了 AgentSociety 的环境模块 validator：

| 检查 | 结果 |
|---|---|
| scanner accepted | 通过 |
| default constructible | 通过 |
| `description()` / `init_description()` | 通过 |
| 80 个通用工具注册 | 通过 |
| `step()` | 通过 |
| CodeGenRouter smoke test | 通过 |
| registry metadata visibility | 未通过（使用 `--no-refresh-metadata`，没有刷新项目 registry） |

validator 的整体 `success=false` 只来自最后一项 registry visibility；代码扫描、工具注册、实例化和 router 挂载均通过。没有刷新或提交 `.agentsociety` 元数据。

## 6. 有效凭据后的重跑方式

先在 AgentSociety checkout 的 `.env` 中配置有效的：

```text
AGENTSOCIETY_LLM_API_BASE=...
AGENTSOCIETY_LLM_API_KEY=...
AGENTSOCIETY_LLM_MODEL=...
```

然后从 ASCII symlink 运行，避免 Ray 重新触发中文路径序列化问题：

```bash
cd /tmp/afi-platform
export WORKSPACE_PATH=/tmp/afi-platform
.venv/bin/python -m afi.cli run-ew \
  /tmp/afi-platform/scenarios/public_information_crisis/public_information_crisis.yaml \
  --run-dir /tmp/afi-platform/runs/pic001_evidence_first \
  --model qwen-plus \
  --as-home /tmp/AgentSociety \
  --audit \
  --out /tmp/afi-platform/results/pic001_evidence_first_audit.html
```

真实 run 成功的最低验收条件：

- `runs/pic001_evidence_first/SOCIETY_STEP.json` 存在且 `completed_step_count=8`；
- `runs/pic001_evidence_first/replay/_schema.json` 和完整 sharded replay 存在；
- `afi audit runs/pic001_evidence_first --out results/pic001_evidence_first_audit.html` 成功；
- `afi awi runs/pic001_evidence_first --json results/pic001_evidence_first_awi.json` 成功；
- 再运行 `rumor_first`，才可以比较两个传播顺序变体。

## 7. 变更范围

本轮变更只涉及 PIC-001 场景、工具实现、专项测试、工具规划和本报告；没有修改主项目 README，也没有执行任何 Git 提交。
