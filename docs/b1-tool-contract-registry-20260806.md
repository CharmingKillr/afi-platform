# B1 工具行为契约注册表（2026-08-06）

> 这份文档补充 `docs/b1-ew-tool-matrix-113-20260806.md`：矩阵回答“工具名由谁实现”，本文件回答“工具调用必须满足什么行为契约”。代码权威来源是 [`afi/world/ew_tools.py`](../afi/world/ew_tools.py) 中的 `EWToolSpec.contract`；不覆盖真实 LLM 自主选择能力。

## 1. 为什么要增加契约层

仅有 `agent_id + request` 的通用 handler，可以证明工具被注册和路由，但不能充分说明：

- 模型应该传哪些字段，哪些字段是必填、枚举或数值范围；
- 这是读取、写入还是外部 provider 边界；
- 谁可以读、谁可以写，写入会改变哪个状态；
- Router 重试会不会重复副作用；
- 结果是否能在 workspace checkpoint、replay 和事件日志中恢复。

因此 B1 现在为 113 个公开工具统一登记以下字段：`input_mode`、`actor_field`、`access`、`required_fields`、`optional_fields`、`permission`、`state_effect`、`idempotency`、`audit_event`。

其中：

- `envelope` 表示仍由 `EWToolSpace(agent_id, request)` 承载，契约先作为迁移和运行前校验；
- `explicit` 表示已进入领域环境，工具签名直接表达核心业务参数；
- `actor_field` 单独记录调用主体；通常是 `agent_id`，旧社交适配器的 `send_message` 使用 `sender_id`。它不再被错误地混入“业务字段”或假设由 Router 自动注入；
- `provider` 只表示请求已经排队到外部能力边界，不表示外部事实已经返回或验证。

## 2. 当前 B1 分层

| 层级 | 数量 | 当前含义 |
|---|---:|---|
| EW 公共目录 | 113 | 名称唯一、分类唯一、每个名称有契约记录 |
| 专用领域 owner | 45 | Planning 6、Blog 6、Billboard 6、Governance 8、Economy 10、Social 2、Landmark 1、Community 6 |
| `EWToolSpace` | 68 | 62 个本地通用工具 + 6 个 provider boundary |
| PIC-001 | 29 | 从 113 个公开工具中精确 allowlist；当前 deterministic 链路 29/29 |

这组数字的正确解读是：`113/113` 是目录和路由覆盖，不是 113 个工具都完成了同等程度的领域验收。62 个 generic local 工具已经具备第一轮导航、记忆、事件、routine、archive、内容和动作状态路径，但仍需逐工具精确签名、跨环境协同和真实 Agent trace；6 个外部 provider 必须等待真实 provider 才能继续验收。

## 3. 本轮新增：CommunitySpace

本轮吸收 PR #2 中 typed 参数、权限边界、状态快照、同 step 幂等和 replay/restore 的实现思路，把以下 6 个工具从 `EWToolSpace` 迁移为独立 owner：

| 工具 | 输入 | 状态/权限 | 可审计结果 |
|---|---|---|---|
| `file_complaint` | `agent_id, content, category, location?`，可带 case/evidence metadata | 创建 `submitted` 投诉；owner 可查看正文，其他 Agent 只能查看状态摘要 | 稳定 complaint id、owner、状态、case metadata、`complaint_submitted` 事件 |
| `check_complaint_status` | `agent_id, complaint_id` | owner 返回完整内容；非 owner 不返回投诉正文；状态枚举为 `submitted/acknowledged/resolved/closed` | 读取事件、`owner_view` 标志、状态快照 |
| `propose_community_event` | `agent_id, title, description, location, starts_at?` | 创建 `proposed` 活动；owner 与创建 step 写入状态；后续状态机预留 `scheduled/cancelled/completed` | 稳定 event id、owner、状态、`community_event_proposed` 事件 |
| `list_community_events` | `agent_id, status?, limit?` | 仅 bounded read；状态过滤只接受合法枚举 | 读取事件、受限返回数量 |
| `rate_agent_trust` | `agent_id, target_id, rating(1..5), reason` | 禁止自评；同一 rater→target 的当前值可替换，但历史事件保留 | 当前 rating、是否替换、旧值、case/artifact 引用 |
| `check_agent_trust` | `agent_id, target_id` | 返回公开聚合，不泄露评分理由 | 平均值、样本数、1–5 分布、读取事件 |

所有写操作采用“同一模拟 step + 同一参数只产生一次副作用”的幂等策略；`COMMUNITY_STATE.json` 保存当前状态、next id、dedup 和事件，`community_event_log.jsonl` 保存事件序列，`replay/community_agent_state.*.jsonl` 保存每 Agent 的 step 快照。

### 3.1 本轮精度修正

对照 PR #2 的 typed/replayable 环境实现复核后，修正了契约登记和运行状态之间的两类偏差：

1. `GovernanceSpace` 的公共 Town Hall alias 与 `read_messages` 实际仍使用
   `agent_id + request`，现在登记为 `envelope`；Blog、Billboard、Community、Planning、Economy
   等直接接收业务参数的工具登记为 `explicit`。
2. 补齐 Planning/Economy 以及 Blog/Billboard/Community 的核心必填字段和可选字段；额外校准
   `send_message.sender_id`、`check_calendar.limit`、`transact_compute_credits.mode`。契约表现在会同时输出
   actor、required/optional fields、permission、state effect、audit event 和 idempotency，避免只登记“工具名”而遗漏模型真正要传的参数。
3. `CommunitySpace` 的 `artifact_id` 已纳入统一 metadata 校验，写入 complaint/event/trust 状态，并进入写事件、摘要读取和 restore；审计 event id 改为单调递增，即使事件日志达到上限并裁剪，后续事件仍不会复用旧 ID。

4. 新增 `validate_tool_arguments()`，校验完整的模型顶层 tool-call（主体字段、显式业务字段或嵌套 `request` 字段及 JSON 类型）；新增 schema parity 测试，逐个对照专用 owner 的实际 `_llm_tools` schema，防止注册表再次漂移。

这一步的意义是把 B1 的验证对象从“能否调用函数”推进到“模型看到的 schema、实际签名、状态快照和 replay 是否指向同一个对象”。

## 4. PIC-001 中的 owner 路由

PIC-001 的场景主线不增加工具数量，只改变 trust 工具的权威承载模块：

```text
29 个公共工具
 ├─ BlogSpace：6
 ├─ BillboardSpace：4（full catalog 仍有 6）
 ├─ GovernanceSpace：8
 ├─ EconomySpace：3
 ├─ SimpleSocialSpaceAuditable：2
 ├─ LandmarkSpace：1
 ├─ CommunitySpace：2（rate/check trust）
 └─ EWToolSpace：3（manifesto / registry / analytics）
```

这样 `rate_agent_trust` 不再把评分写入通用 record，`check_agent_trust` 也不会读取另一份影子 trust map。PIC-001 的证据链仍然是：私信核实 → Blog 证据状态 → Billboard 公开传播 → Town Hall 治理 → Economy 激励 → Community trust / final report / replay。

## 5. 机器校验与验证命令

契约注册表提供：

```python
from afi.world.ew_tools import (
    tool_contract_rows,
    render_tool_contract_markdown,
    validate_tool_arguments,
    validate_tool_request,
)
```

`validate_tool_request()` 校验业务 payload：对 `EWToolSpace` / Governance 的 envelope 工具，它校验嵌套 `request`；对显式领域工具，它校验不含主体字段的业务参数。`validate_tool_arguments()` 面向完整 LLM 顶层参数，额外校验主体字段（例如 `agent_id` 或 `sender_id`）。这两个函数只负责 schema 级失败前置；领域 owner 仍负责更严格的权限、枚举、状态机和跨对象规则。

```bash
cd /path/to/afi-platform
PYTHON_PATH=$(sed -n 's/^PYTHON_PATH=//p' ../.env | head -n 1)
PYTHON_PATH=${PYTHON_PATH:-python3}
"$PYTHON_PATH" -m pytest -q
"$PYTHON_PATH" scenarios/public_information_crisis/verify_tool_chain.py \
  --output runs/pic001_deterministic_tool_chain_schema_parity_20260806/summary.json
```

本轮离线证据：全量测试 `121 passed`，新增 generic dispatch/domain lifecycle 回归和结构化上传类型校验；其中包含对 113 项目录中 45 个专用工具的 owner schema parity 检查。新的 deterministic PIC-001 结果为 `29/29` 工具、`43` 次直接调用、`0` 次失败、Governance `1→2`、4/5 for、Community restore 成功、`pass=true`。这些都是确定性工具/状态验证，不是新的 LLM 实验。

精度修正后的复跑结果保持不变：`29/29` 公共工具、`43` 次调用、`0` 次失败、`pass=true`；新增断言确认 Community 的 `artifact_id`、evidence references、restore 和单调审计事件 ID 均可追溯。

## 6. 仍然需要确认的边界

- 62 个 generic local 工具已开始按 navigation、memory、events、routines、identity 等领域拆分；不能把第一轮状态路径或本注册表的存在等同于完整领域实现完成。
- `evidence_refs` 仍主要是本地引用和格式/状态校验，外部内容真实可复核需要 resolver/provider。
- PIC-001 仍未重新启动真实 LLM 自主 run；历史 `pid.status=completed` 不改变“自主 mutation/governance 尚不稳定”的结论。
- 本轮未使用真实地图、道路和 `.pb`，`list_landmarks` 仍是文字地标目录。
