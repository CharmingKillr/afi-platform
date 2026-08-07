# afi-platform 整合 PR 说明

> 整合日期：2026-08-07
>
> 目标：将 EW 公开工具目录、PIC-001 验证场景，以及之前其他协作者已经完成的平台能力整合到同一条可复现、可审查的分支中，便于后续从 PR 拉取后继续开发。

## 1. 本次整合范围

### 我们这条线的能力

- EW 公开工具目录与契约：113/113 名称、唯一 owner、路由和 schema 校验。
- `EWToolSpace` 的 62 个 generic 工具第一轮领域化状态路径，包括导航/地标查询、记忆、事件、routine、archive、上传、neural link、能量和动作审计。
- Blog、Billboard、Community 与治理/经济/社交环境的跨域工具契约。
- PIC-001“公共信息危机与治理响应”场景、确定性工具链验证器、Contract Mode 和场景报告。
- 场景级文档、工具矩阵、工具构建审计和契约登记表。

### 之前其他工作线的能力

- `EWMobilitySpace`：基于命名地标坐标的轻量移动和轨迹回放。
- AWI M3/M6/M7：读取移动、公开表达和 typed relationship replay；没有对应 replay 时保留 proxy 回退。
- `RelationshipSpace`：关系类型、关系操作、状态持久化和 replay。
- `BillboardSpace`：公开帖子、reply、reaction、owner 权限、软删除和事件审计。
- pydantic 场景 DSL 校验。
- Concordia backend adapter。
- L1/L2/L3 eval、群体行为、因果可视化和 NLG 审计模块。

## 2. 地标与地图的整合边界

项目保留两层空间语义，避免把文字地标目录误报成真实物理地图：

```text
afi/world/landmarks.py
  └─ EW 业务地标语义：BookWorm / Ad Tower / Agent Billboard / Town Hall / Victory Arch
       ├─ LandmarkSpace：文字目录和地点说明
       └─ EWToolSpace：导航工具的地标名称校验和位置状态

custom/envs/ew_mobility_space.py
  └─ 可选的 32 个合成坐标地标、移动工具和 mobility replay
       └─ afi/audit/awi.py：M3 computed；没有 replay 时回退 proxy
```

`EWMobilitySpace` 已注册到场景 builder，并有单测和 AWI reader，但当前 `ew_full.yaml` 与 PIC-001 默认不启用它。PIC-001 仍明确使用 `landmark_directory`，`mobility: disabled`。这样本次 PR 的 deterministic PIC-001 结论只证明信息/治理工具链，不把未执行的移动过程算作地图验证。

真实城市 `.pb` 地图、道路网络、POI/AOI 数据和模型运行产物不进入本 PR。后续如果要验证空间距离对传播延迟的影响，应先统一 5 个 EW 业务地标与 32 个移动地标的 ID/坐标来源，再建立独立 mobility scenario。

## 3. 验证结果

本地离线检查包括：

- 全量 pytest：`121 passed`；
- 严格警告模式：`pytest -W error` 通过；
- Python `compileall` 通过；
- YAML 配置全部可加载；
- EW 工具目录：`113/113`，重复 owner 为 `0`；
- PIC-001 deterministic：`29/29` 工具、`43` 次调用、`0` 次失败、Governance `1 → 2`、`pass=true`；
- `git diff --check` 通过。

以上是离线契约和确定性场景证据，不等同于真实 LLM 自主实验、真实地图实验、外部 Provider 验证或真实 Concordia 运行。

## 4. 有意不纳入本 PR 的内容

`deploy/local-llm/` 是绑定 `Teleai_gpu` 服务器路径的本地 vLLM 运维脚本。它对模型复现实验有帮助，但不属于平台工具和场景核心代码，本次先不纳入整合 PR；模型权重、日志、PID、API key 和运行产物均不提交。

Billboard 的 Agent-facing `SKILL.md` 随 BillboardSpace 一起纳入，因为它是工具契约到 Agent 使用行为的直接适配层。
