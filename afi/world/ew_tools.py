"""Authoritative public EW tool catalog used by B1 coverage checks.

Source: EmergenceAI/Emergence-World ``tools/README.md`` (2026-07-15).
The public table currently contains 113 unique names although the project
describes the evolving private/runtime catalog as "120+".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

EW_TOOL_CATEGORIES = {
    "navigation": "go_to_place go_home run_to_place go_to_coordinates turn_towards get_distance_to list_agents list_landmarks get_nearby follow_agent",
    "communication": "say_to_agent send_message read_messages think_aloud",
    "memory": "add_to_longterm_memory remove_from_memory retrieve_specific_memories add_to_soul remove_from_soul write_diary search_diary_for_keywords show_diary_entries_from_day",
    "planning": "add_todo complete_todo list_todo add_to_calendar check_calendar remove_from_calendar",
    "expression": "show_emoticon set_mood_and_terminate assign_relationship put_on_fire",
    "governance": "submit_townhall_proposal list_proposals read_townhall_proposal vote_on_proposal comment_on_proposal update_proposal read_constitution submit_final_report",
    "research": "do_deep_research_on_internet todays_news_from_human_world web_fetch browse_scientific_papers publish_to_archive search_archive archive_index",
    "economy": "submit_grant_pitch vote_for_pitch list_credit_pitches deposit_credits_to_bank withdraw_credits_from_bank take_bank_loan repay_bank_loan check_bank_balance transact_compute_credits victory_arch_pitch_winners",
    "billboard": "add_to_billboard read_billboard edit_billboard delete_from_billboard reply_to_billboard react_to_billboard",
    "analytics": "extract_code_for_tool read_agent_manifesto browse_tool_registry check_weather tool_usage_analytics_by_character overall_tool_usage_analytics_by_date social_event_history",
    "community": "file_complaint check_complaint_status propose_community_event list_community_events rate_agent_trust check_agent_trust pray read_advertisements post_advertisements",
    "self_care": "self_care idle recharge_energy",
    "content": "write_blog update_blog delete_blog comment_on_blog list_blogs read_blog generate_image execute_python_code_tool upload_data_for_sharing take_picture",
    "social_physical": "physical_action dance neural_link_request_memory neural_link_share_memory",
    "identity": "change_name read_personality update_personality_line",
    "events": "create_personal_event invite_to_event accept_event_invitation decline_event_invitation review_event rsvp_to_event event_present event_respond",
    "routines": "create_routine run_routine list_routines delete_routine",
    "building": "put_brick_in_pixel",
    "utility": "ignore",
}

EW_TOOLS_BY_CATEGORY = {
    category: tuple(names.split()) for category, names in EW_TOOL_CATEGORIES.items()
}
EW_PUBLIC_TOOLS = tuple(
    name for names in EW_TOOLS_BY_CATEGORY.values() for name in names
)

assert len(EW_PUBLIC_TOOLS) == 113
assert len(set(EW_PUBLIC_TOOLS)) == 113


@dataclass(frozen=True)
class EWToolSpec:
    """One auditable catalog entry, independent from router implementation."""

    name: str
    category: str
    purpose: str
    owner: str
    implementation: str
    validation: str


_CATEGORY_PURPOSES = {
    "navigation": "移动、定位或观察世界中的智能体与地标",
    "communication": "智能体间通信或表达内部思考",
    "memory": "维护长期记忆、核心信念和日记",
    "planning": "维护个人待办事项和日历",
    "expression": "表达情绪、关系或具身动作",
    "governance": "参与提案、投票、宪法和执行报告流程",
    "research": "获取、检索或发布知识",
    "economy": "管理 ComputeCredits、银行业务和贡献奖励",
    "billboard": "维护公共公告及其互动",
    "analytics": "读取工具、智能体和社会活动分析信息",
    "community": "处理投诉、社区活动、信任和公共服务",
    "self_care": "休息、恢复能量或进行认知维护",
    "content": "创建、读取、更新或共享数字内容",
    "social_physical": "执行社交性或物理互动",
    "identity": "读取或更新智能体身份与人格",
    "events": "创建、邀请、参加和评价社会活动",
    "routines": "定义和执行可复用行为流程",
    "building": "在世界中创建持久化结构",
    "utility": "显式执行无操作或忽略行为",
}

_SPECIALIZED_OWNERS = {
    "list_landmarks": "LandmarkSpace",
    "send_message": "SimpleSocialSpaceAuditable",
    **{name: "PlanningSpace" for name in EW_TOOLS_BY_CATEGORY["planning"]},
    **{name: "EconomySpace" for name in EW_TOOLS_BY_CATEGORY["economy"]},
}
_EXTERNAL_PROVIDER_TOOLS = {
    "do_deep_research_on_internet",
    "todays_news_from_human_world",
    "web_fetch",
    "browse_scientific_papers",
    "check_weather",
    "generate_image",
}


def _purpose(name: str, category: str) -> str:
    action = name.replace("_", " ")
    return f"{_CATEGORY_PURPOSES[category]}；具体动作：{action}。"


EW_TOOL_SPECS = tuple(
    EWToolSpec(
        name=name,
        category=category,
        purpose=_purpose(name, category),
        owner=_SPECIALIZED_OWNERS.get(name, "EWToolSpace"),
        implementation=(
            "external_adapter"
            if name in _EXTERNAL_PROVIDER_TOOLS
            else "specialized"
            if name in _SPECIALIZED_OWNERS
            else "generic_local"
        ),
        validation=(
            "provider_boundary_only"
            if name in _EXTERNAL_PROVIDER_TOOLS
            else "registered_and_router_tested"
            if name in {"list_landmarks", "send_message"}
            else "contract_and_unit_tested"
        ),
    )
    for category, names in EW_TOOLS_BY_CATEGORY.items()
    for name in names
)
EW_TOOL_SPEC_BY_NAME = {spec.name: spec for spec in EW_TOOL_SPECS}


def tool_catalog_rows() -> list[dict]:
    """Return JSON-serializable rows for reports, APIs, and progress dashboards."""
    return [asdict(spec) for spec in EW_TOOL_SPECS]


def render_tool_catalog_markdown() -> str:
    """Render all public tools for a human review or project progress report."""
    labels = {
        "specialized": "专用实现",
        "generic_local": "本地通用实现",
        "external_adapter": "外部能力适配器",
        "contract_and_unit_tested": "契约与单元测试通过",
        "registered_and_router_tested": "注册与路由验证通过，尚缺独立行为测试",
        "provider_boundary_only": "仅适配边界通过，需接入真实服务验证",
    }
    lines = [
        "# EW 工具定义、注册与有效性目录",
        "",
        "| 工具 | 分类 | 用途 | 注册责任模块 | 实现 | 有效性 |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        "| `{}` | {} | {} | `{}` | {} | {} |".format(
            spec.name,
            spec.category,
            spec.purpose,
            spec.owner,
            labels[spec.implementation],
            labels[spec.validation],
        )
        for spec in EW_TOOL_SPECS
    )
    return "\n".join(lines) + "\n"
