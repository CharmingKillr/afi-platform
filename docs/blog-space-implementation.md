# BlogSpace：B1 内容工具领域化实现

> 2026-07-27。基于 `codex/integrate-pr1-pr2` 的 `c0bd7d7`，将 6 个 EW 内容工具从 `EWToolSpace` 的通用请求分发迁移到专用 `BlogSpace`。

> **2026-08-06 口径更新**：本文件保留 2026-07-27 的 BlogSpace 历史快照；按当前工作树重新核对，EW 公开目录的 owner 分布已经是 33 个专用实现、80 个 `EWToolSpace` 通用实现。完整审计见 [`b1-tool-build-audit-20260806.md`](b1-tool-build-audit-20260806.md)。

## 目标

B1 的完成标准不只是把 113 个公开名称注册到 AgentSociety，而是逐领域补齐严格参数、权限、状态、幂等、持久化、审计和测试。本次选择内容域作为下一块专用领域包，覆盖：

- `write_blog`
- `update_blog`
- `delete_blog`
- `comment_on_blog`
- `list_blogs`
- `read_blog`

## 实现内容

`BlogSpace` 提供：

- `title`、`content`、`visibility`、`status` 的严格参数和长度约束；
- `public/private` 可见性；
- `draft/published` 生命周期状态；
- owner-only 更新和删除；
- 私有博客对其他 Agent 的读取和评论隔离；
- 评论数量和内容长度上限；
- 同 step、同参数写操作去重；
- workspace 保存与恢复；
- 每步 `blog_posts`、`published_posts`、`blog_comments` replay 汇总；
- `blog_created`、`blog_updated`、`blog_deleted`、`blog_commented` 事件记录。

## 目录归属变化

| 维度 | 2026-07-27 快照 | 2026-08-06 当前 |
|-|-|-|
| EW 公开工具 | 113 | 113 |
| 专用实现 | 24 | 33 |
| `EWToolSpace` 通用实现 | 89 | 80 |
| Blog 工具 owner | `EWToolSpace` | `BlogSpace` |

目录覆盖仍保持 113/113，且完整场景中每个工具只有一个实现者。

## 当前边界

- `draft/published` 已建模，但公开目录没有独立的 `submit_for_review` / `approve` 工具，因此尚未建成完整的审核工作流；
- 写操作仍使用 step 级幂等，后续需要接入稳定的 tool-call/idempotency key；
- 调用身份目前由 AgentSociety 传入的 `agent_id` 表达，后续需要验证不可伪造的调用上下文；
- 真实 LLM Agent trace 和长时程博客传播实验仍待补充；
- M6 AWI 仍需读取 BlogSpace 的传播状态，当前只具备领域状态和 replay 基础。

## 验收

除原有 B1 测试外，新增内容域测试覆盖：

- 专用注册和通用空间排重；
- 公开博客可读、owner 权限和私有隔离；
- draft → published 状态变化；
- 评论写入和同 step 幂等；
- 空标题、非法 visibility 等参数错误；
- workspace 恢复后博客与评论仍可读。
