# PIC-001 新一轮验证报告：Contract Mode 与本地 Qwen3.6-27B

日期：2026-08-04
场景：`PIC-001 / public_information_crisis / evidence_first`
模型：`qwen36-27b`（本地 vLLM，`http://127.0.0.1:18000/v1`）
状态：`CONTRACT_MODE_PASSED / AUTONOMY_MODE_REQUIRES_FURTHER_OPTIMIZATION`

## 1. 本轮目标

上一轮真实运行的主要问题不是 29 个工具都不可用，而是 Contract 测试和 Agent 自主行为混在一起：

```text
长自然语言 intervene
  → helper 规划
  → ask_environment
  → 自由 Python codegen
  → 多次重试 / 参数丢失 / 业务闭环不完整
```

本轮先按 P0 方案把“工具契约验证”单独做成可验收的 Contract Mode，再用 Autonomy smoke 判断本地模型的自由工具选择是否正常。

## 2. 已实施的优化

### 2.1 结构化 Contract 路由

PIC-001 的显式 `Call tool(...)` 现在经过：

```text
Call 文本
  → Python AST 解析
  → literal 参数解析（不执行任意代码）
  → 注册工具名校验
  → 工具签名 / 关键字参数归一化
  → 直接调用真实 Env 工具
  → 返回 status + 结果
  → 写入结构化审计日志
```

该路径只对明确的单条 PIC-001 Contract 调用生效；普通自然语言请求仍保留 AgentSociety 的原生 LLM codegen，因此不会把 Contract 结果误当作 Agent 自主能力。

### 2.2 运行模式分离

`afi/world/scenario.py` 新增运行模式处理：

- `contract`：过滤自主 `run` 窗口，只执行 YAML 中的 8 个显式 checkpoint；
- `autonomy`：保留 AgentSociety 的自然语言和模拟小时，用于研究 Agent 自主行为；
- `--max-checkpoints N`：给 smoke test 限定 checkpoint 前缀，避免未经验证就启动长实验。

### 2.3 可验收状态与产物

每次 Contract 调用写入：

```text
runs/<run_id>/artifacts/pic001_structured_call_log.jsonl
```

新 verifier 读取场景 YAML 作为 expected-call manifest，并逐项检查：

- 工具名是否一致；
- 参数字典是否一致；
- 调用顺序是否一致；
- 返回 `status` 是否成功；
- 是否有缺失或意外调用；
- 29 个公共工具是否全部出现。

每个 checkpoint 写入独立 JSON，汇总写入：

```text
runs/<run_id>/contract_audit/scenario_status.json
```

### 2.4 本地模型重试上限

PIC-001 本地 `.env` 增加：

```text
AFI_PIC001_CODEGEN_MAX_RETRIES=2
```

它把本地模型的自由 codegen 修复上限从上游默认 10 次收紧到 2 次，避免一条错误请求占用数分钟后才暴露失败。该限制只在 PIC-001 自定义环境加载时生效。

## 3. LLM preflight 结果

| 检查项 | 结果 |
|---|---|
| `GET /v1/models` | HTTP 200；目标 `qwen36-27b` 存在 |
| 普通 chat completion | HTTP 200；返回非空内容 |
| structured tool request | HTTP 200；返回 1 个 tool call |
| API key | 本地 `afi-local` 可用；没有打印或写入外部密钥 |

结论：模型服务和 OpenAI-compatible API 正常。

## 4. Smoke test 结果

运行目录：

```text
runs/pic001_contract_qwen36_27b_smoke_20260804
```

第一个 baseline checkpoint 结果：

```text
9 / 9 调用成功
工具名错配：0
参数错配：0
```

该 smoke 只验证前缀，不能作为完整场景通过；通过 `--allow-partial` 标记为 `passed_partial`。

随后执行的 Autonomy smoke 目录：

```text
runs/pic001_autonomy_qwen36_27b_llm_smoke_20260804
```

该运行确实进入了 AgentSociety 自主一小时，trace 中出现多个 `llm.completion` span，模型名为 `qwen36-27b`，且 HTTP 调用返回成功。但 Agent 1 的自由 codegen 连续进行错误修复，尚未稳定形成业务工具结果。为避免原有 10 次重试继续拖长实验，本轮在 bounded smoke 阶段优雅终止，运行状态记为 `terminated`。

这一区分很重要：

```text
endpoint 可用             = 通过
Contract 工具路由可用      = 通过
Autonomy 自由 codegen 稳定  = 尚未通过
```

## 5. 完整 Contract Mode 结果

运行目录：

```text
runs/pic001_contract_qwen36_27b_20260804
```

审计目录：

```text
runs/pic001_contract_qwen36_27b_20260804/contract_audit
```

审计汇总：

| 指标 | 结果 |
|---|---:|
| checkpoint | 8 / 8 passed |
| 预期显式调用 | 46 |
| 实际显式调用 | 46 |
| 调用失败 | 0 |
| 工具名 / 参数错配 | 0 |
| 公共工具覆盖 | 29 / 29 |
| 意外调用 | 0 |
| 进程状态 | `completed` |
| 场景状态 | `passed` |

这轮覆盖的核心链路为：

```text
baseline discovery
  → private messages
  → two public Blogs
  → Billboard post / reply / reaction
  → authoritative Town Hall proposal
  → 70% governance vote
  → two Victory Arch pitches / votes
  → trust / final report / analytics
  → temporary Blog create/delete lifecycle
```

因此，当前可以正式确认的是：

> PIC-001 的 29 个工具在结构化 Contract Mode 下能够被注册、路由、执行和逐调用审计；跨域对象和参数的调用顺序也能够被复核。

## 6. 尚未通过的部分与下一步

当前不应宣布“完整 LLM 场景闭环已通过”，因为 Autonomy Mode 仍暴露自由 codegen 可靠性问题。下一步按以下顺序推进：

1. 将 Autonomy Mode 的 mutation 工具改成原生 structured/function call 或 JSON Schema 输出；
2. 对自然语言 codegen 增加 `syntax_error / schema_error / unknown_id / provider_error` 分类和 step 级 fail-fast；
3. 为自由 codegen 加入只读工具优先、mutation 工具分阶段暴露策略；
4. 先用 1 小时、单 Agent smoke 验证稳定性，再扩大到 5 Agent / 8 小时；
5. Autonomy smoke 通过后，再分别跑 `evidence_first` 与 `rumor_first`，每个至少 3 个 seed。

本轮没有执行 Git 提交、推送或覆盖历史 run。
