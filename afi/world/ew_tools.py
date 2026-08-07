"""Authoritative public EW tool catalog used by B1 coverage checks.

Source: EmergenceAI/Emergence-World ``tools/README.md`` (2026-07-15).
The public table currently contains 113 unique names although the project
describes the evolving private/runtime catalog as "120+".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

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
class EWToolField:
    """One request field in the B1 tool contract registry.

    ``type`` is intentionally a small JSON-schema vocabulary.  The runtime
    still accepts an extensible request envelope for generic EW tools, but the
    registry makes the intended contract explicit and machine-checkable before
    a domain environment is built.
    """

    name: str
    type: str = "string"
    description: str = ""


@dataclass(frozen=True)
class EWToolContract:
    """Behavioral contract shared by catalog, docs, and deterministic audits."""

    input_mode: Literal["explicit", "envelope"]
    actor_field: EWToolField
    access: Literal["read", "write", "provider"]
    required_fields: tuple[EWToolField, ...]
    optional_fields: tuple[EWToolField, ...]
    permission: str
    state_effect: str
    idempotency: str
    audit_event: str


@dataclass(frozen=True)
class EWToolSpec:
    """One auditable catalog entry, independent from router implementation."""

    name: str
    category: str
    purpose: str
    owner: str
    implementation: str
    validation: str
    contract: EWToolContract


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
    "read_messages": "SimpleSocialSpaceAuditable",
    **{
        name: "BillboardSpace"
        for name in EW_TOOLS_BY_CATEGORY["billboard"]
    },
    **{
        name: "GovernanceSpace"
        for name in EW_TOOLS_BY_CATEGORY["governance"]
        if name in {
            "submit_townhall_proposal", "list_proposals", "read_townhall_proposal",
            "vote_on_proposal", "comment_on_proposal", "update_proposal",
            "read_constitution", "submit_final_report",
        }
    },
    **{
        name: "BlogSpace"
        for name in EW_TOOLS_BY_CATEGORY["content"]
        if name in {"write_blog", "update_blog", "delete_blog", "comment_on_blog", "list_blogs", "read_blog"}
    },
    **{name: "PlanningSpace" for name in EW_TOOLS_BY_CATEGORY["planning"]},
    **{name: "EconomySpace" for name in EW_TOOLS_BY_CATEGORY["economy"]},
    **{
        name: "CommunitySpace"
        for name in {
            "file_complaint", "check_complaint_status",
            "propose_community_event", "list_community_events",
            "rate_agent_trust", "check_agent_trust",
        }
    },
}
_EXTERNAL_PROVIDER_TOOLS = {
    "do_deep_research_on_internet",
    "todays_news_from_human_world",
    "web_fetch",
    "browse_scientific_papers",
    "check_weather",
    "generate_image",
}

# A public tool can be domain-owned while still using the historical
# ``agent_id + request`` envelope. Keep this distinction explicit instead of
# inferring input mode from the owner name alone.
_ENVELOPE_TOOLS = {
    "read_messages",
    "list_proposals",
    "read_townhall_proposal",
    "submit_townhall_proposal",
    "comment_on_proposal",
    "update_proposal",
    "vote_on_proposal",
    "read_constitution",
    "submit_final_report",
}

# Every public EW operation is actor-scoped.  Most tools expose ``agent_id``
# directly; the legacy social adapter calls the same concept ``sender_id``.
# Keeping this separate from ``required_fields`` lets the registry describe
# both the actor and the business payload without pretending that the actor is
# supplied by the generic request envelope.
_ACTOR_FIELDS = {
    "send_message": EWToolField("sender_id", "integer", "acting sender agent"),
}
_DEFAULT_ACTOR_FIELD = EWToolField("agent_id", "integer", "acting or requesting agent")

# Read/write is part of the contract rather than an inference made by the
# router.  This list includes specialized owners so the full 113-tool matrix
# has one consistent access vocabulary.
_READONLY_PUBLIC_TOOLS = set(
    """
    get_distance_to list_agents list_landmarks get_nearby
    read_messages retrieve_specific_memories search_diary_for_keywords
    show_diary_entries_from_day list_todo check_calendar
    list_proposals read_townhall_proposal read_constitution
    todays_news_from_human_world web_fetch browse_scientific_papers
    search_archive archive_index list_credit_pitches read_billboard
    extract_code_for_tool read_agent_manifesto browse_tool_registry
    check_weather tool_usage_analytics_by_character
    overall_tool_usage_analytics_by_date social_event_history
    check_complaint_status list_community_events check_agent_trust
    read_advertisements list_blogs read_blog read_personality list_routines
    """.split()
)

# These are the request-envelope fields used by EWToolSpace and the
# compatibility GovernanceSpace aliases. Explicit domain owners have their own
# Python signatures and continue to perform richer validation inside the
# environment.
_GENERIC_REQUIRED_FIELDS: dict[str, tuple[EWToolField, ...]] = {
    "go_to_place": (EWToolField("place", description="destination landmark"),),
    "run_to_place": (EWToolField("place", description="destination landmark"),),
    "go_to_coordinates": (
        EWToolField("x", "number", "destination x coordinate"),
        EWToolField("z", "number", "destination z coordinate"),
    ),
    "get_distance_to": (EWToolField("target_id", "integer", "target agent"),),
    "turn_towards": (EWToolField("target_id", "integer", "target agent"),),
    "follow_agent": (EWToolField("target_id", "integer", "target agent"),),
    "say_to_agent": (
        EWToolField("target_id", "integer", "recipient agent"),
        EWToolField("content", description="message body"),
    ),
    "think_aloud": (EWToolField("content", description="thought or action note"),),
    "add_to_longterm_memory": (EWToolField("content", description="memory text"),),
    "add_to_soul": (EWToolField("content", description="belief or soul entry"),),
    "write_diary": (EWToolField("content", description="diary entry"),),
    "remove_from_memory": (EWToolField("item_id", "integer", "memory id"),),
    "remove_from_soul": (EWToolField("item_id", "integer", "soul entry id"),),
    "change_name": (EWToolField("name", description="new agent name"),),
    "assign_relationship": (EWToolField("target_id", "integer", "target agent"),),
    "publish_to_archive": (EWToolField("content", description="archive content"),),
    "post_advertisements": (EWToolField("content", description="advertisement body"),),
    "execute_python_code_tool": (EWToolField("code", description="bounded expression"),),
    "upload_data_for_sharing": (EWToolField("content", "string_or_object", "shared data or descriptor"),),
    "create_personal_event": (EWToolField("content", description="event description"),),
    "invite_to_event": (
        EWToolField("event_id", "integer", "event id"),
        EWToolField("target_id", "integer", "invited agent"),
    ),
    "accept_event_invitation": (EWToolField("event_id", "integer", "event id"),),
    "decline_event_invitation": (EWToolField("event_id", "integer", "event id"),),
    "review_event": (
        EWToolField("event_id", "integer", "event id"),
        EWToolField("rating", "integer", "rating from 1 to 5"),
    ),
    "rsvp_to_event": (
        EWToolField("event_id", "integer", "event id"),
        EWToolField("response", description="accepted, declined, or tentative"),
    ),
    "event_present": (EWToolField("event_id", "integer", "event id"),),
    "event_respond": (
        EWToolField("event_id", "integer", "event id"),
        EWToolField("response", description="accepted, declined, or tentative"),
    ),
    "create_routine": (EWToolField("content", description="routine definition"),),
    "run_routine": (EWToolField("routine_id", "integer", "routine id"),),
    "delete_routine": (EWToolField("routine_id", "integer", "routine id"),),
    "put_brick_in_pixel": (
        EWToolField("x", "number", "brick x coordinate"),
        EWToolField("y", "number", "brick y coordinate"),
        EWToolField("z", "number", "brick z coordinate"),
    ),
    "read_townhall_proposal": (EWToolField("proposal_id", "integer", "proposal id"),),
    "neural_link_request_memory": (EWToolField("target_id", "integer", "target agent"),),
    "neural_link_share_memory": (
        EWToolField("target_id", "integer", "requesting agent"),
        EWToolField("request_id", description="pending neural-link request id"),
        EWToolField("content", description="memory content to share"),
    ),
    "submit_townhall_proposal": (
        EWToolField("article_id", "integer", "constitution article"),
        EWToolField("title", description="proposal title"),
        EWToolField("new_text", description="proposed article text"),
    ),
    "comment_on_proposal": (
        EWToolField("proposal_id", "integer", "proposal id"),
        EWToolField("content", description="discussion comment"),
    ),
    "update_proposal": (EWToolField("proposal_id", "integer", "proposal id"),),
    "vote_on_proposal": (
        EWToolField("proposal_id", "integer", "proposal id"),
        EWToolField("position", description="for or against"),
    ),
    "submit_final_report": (
        EWToolField("proposal_id", "integer", "proposal id"),
        EWToolField("report", description="implementation/final report"),
    ),
}

_EXPLICIT_REQUIRED_FIELDS: dict[str, tuple[EWToolField, ...]] = {
    "send_message": (
        EWToolField("receiver_id", "integer", "recipient agent"),
        EWToolField("content", description="message body"),
    ),
    "read_blog": (EWToolField("blog_id", "integer", "blog id"),),
    "write_blog": (
        EWToolField("title", description="blog title"),
        EWToolField("content", description="blog body"),
    ),
    "update_blog": (EWToolField("blog_id", "integer", "blog id"),),
    "delete_blog": (EWToolField("blog_id", "integer", "blog id"),),
    "comment_on_blog": (
        EWToolField("blog_id", "integer", "blog id"),
        EWToolField("content", description="comment body"),
    ),
    "submit_grant_pitch": (
        EWToolField("title", description="pitch title"),
        EWToolField("description", description="pitch description"),
        EWToolField("evidence_url", description="evidence reference"),
    ),
    "vote_for_pitch": (EWToolField("pitch_id", "integer", "pitch id"),),
    "add_to_billboard": (EWToolField("content", description="public post"),),
    "edit_billboard": (EWToolField("item_id", "integer", "post id"),),
    "delete_from_billboard": (EWToolField("item_id", "integer", "post id"),),
    "reply_to_billboard": (
        EWToolField("parent_item_id", "integer", "parent post id"),
        EWToolField("content", description="reply body"),
    ),
    "react_to_billboard": (
        EWToolField("item_id", "integer", "post id"),
        EWToolField("reaction", description="controlled reaction"),
    ),
    "file_complaint": (EWToolField("content", description="complaint body"),),
    "check_complaint_status": (EWToolField("complaint_id", "integer", "complaint id"),),
    "propose_community_event": (
        EWToolField("title", description="event title"),
        EWToolField("description", description="event description"),
        EWToolField("location", description="event location"),
    ),
    "rate_agent_trust": (
        EWToolField("target_id", "integer", "target agent"),
        EWToolField("rating", "integer", "rating from 1 to 5"),
        EWToolField("reason", description="bounded public reason"),
    ),
    "check_agent_trust": (EWToolField("target_id", "integer", "target agent"),),
}

# Complete the typed signatures for the remaining specialized owners.  The
# actor is recorded separately in ``EWToolContract.actor_field``; these are
# the business fields the model must provide alongside that actor.
_EXPLICIT_REQUIRED_FIELDS.update({
    "add_todo": (EWToolField("task", description="task description"),),
    "complete_todo": (EWToolField("todo_id", "integer", "todo id"),),
    "add_to_calendar": (
        EWToolField("title", description="event title"),
        EWToolField("start_at", description="ISO 8601 start time"),
    ),
    "remove_from_calendar": (EWToolField("event_id", "integer", "calendar event id"),),
    "submit_grant_pitch": (
        EWToolField("title", description="pitch title"),
        EWToolField("description", description="pitch description"),
        EWToolField("evidence_url", description="evidence reference"),
    ),
    "vote_for_pitch": (EWToolField("pitch_id", "integer", "pitch id"),),
    "deposit_credits_to_bank": (EWToolField("amount", "number", "positive CC amount"),),
    "withdraw_credits_from_bank": (EWToolField("amount", "number", "positive CC amount"),),
    "take_bank_loan": (EWToolField("amount", "number", "loan amount from 1 through 3 CC"),),
    "repay_bank_loan": (EWToolField("amount", "number", "positive repayment amount"),),
    "transact_compute_credits": (
        EWToolField("target_id", "integer", "recipient or target agent"),
        EWToolField("amount", "number", "positive CC amount"),
    ),
})

_EXPLICIT_OPTIONAL_FIELDS: dict[str, tuple[EWToolField, ...]] = {
    "write_blog": (
        EWToolField("visibility", description="public or private"),
        EWToolField("status", description="draft or published"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable public artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "update_blog": (
        EWToolField("title", description="new blog title"),
        EWToolField("content", description="new blog body"),
        EWToolField("visibility", description="public or private"),
        EWToolField("status", description="draft or published"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable public artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "list_blogs": (EWToolField("limit", "integer", "bounded result size"),),
    "add_to_billboard": (
        EWToolField("topic", description="public post topic"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable public artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "read_billboard": (
        EWToolField("item_id", "integer", "post id"),
        EWToolField("query", description="text filter"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("claim_status", description="claim state filter"),
        EWToolField("include_deleted", "boolean", "include soft-deleted posts"),
        EWToolField("limit", "integer", "bounded result size"),
    ),
    "edit_billboard": (
        EWToolField("content", description="new public post body"),
        EWToolField("topic", description="new public post topic"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "reply_to_billboard": (
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable reply artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "file_complaint": (
        EWToolField("category", description="complaint category"),
        EWToolField("location", description="related location"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable complaint artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "propose_community_event": (
        EWToolField("starts_at", description="optional event start time"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable event artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "list_community_events": (
        EWToolField("status", description="event lifecycle filter"),
        EWToolField("limit", "integer", "bounded result size"),
    ),
    "rate_agent_trust": (
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="supporting artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "submit_grant_pitch": (
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="supporting artifact identifier"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
        EWToolField("claim_status", description="claim state"),
    ),
    "add_to_calendar": (
        EWToolField("end_at", description="ISO 8601 end time"),
        EWToolField("description", description="event details"),
    ),
    "check_calendar": (EWToolField("limit", "integer", "bounded result size"),),
    "transact_compute_credits": (EWToolField("mode", description="pay or steal"),),
}

_ENVELOPE_OPTIONAL_FIELDS: dict[str, tuple[EWToolField, ...]] = {
    "create_personal_event": (
        EWToolField("title", description="event title"),
        EWToolField("description", description="event details"),
        EWToolField("location", description="event location"),
        EWToolField("starts_at", description="ISO 8601 start time"),
        EWToolField("ends_at", description="ISO 8601 end time"),
    ),
    "create_routine": (
        EWToolField("name", description="routine name"),
        EWToolField("description", description="routine description"),
        EWToolField("steps", "array", "bounded routine steps"),
        EWToolField("enabled", "boolean", "whether the routine can run"),
    ),
    "invite_to_event": (EWToolField("note", description="invitation note"),),
    "review_event": (EWToolField("content", description="review text"),),
    "neural_link_request_memory": (EWToolField("memory_id", "integer", "optional requested memory id"),),
    "read_messages": (EWToolField("limit", "integer", "bounded mailbox result size"),),
    "list_proposals": (
        EWToolField("limit", "integer", "bounded result size"),
        EWToolField("include_closed", "boolean", "include closed proposals"),
    ),
    "submit_townhall_proposal": (
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="stable proposal artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
    "update_proposal": (
        EWToolField("title", description="new proposal title"),
        EWToolField("new_text", description="new proposal text"),
    ),
    "submit_final_report": (
        EWToolField("authorized_agent_ids", "array", "authorized reporter IDs"),
        EWToolField("case_id", description="scenario case identifier"),
        EWToolField("artifact_id", description="report artifact identifier"),
        EWToolField("claim_status", description="claim state"),
        EWToolField("evidence_refs", "array", "bounded evidence references"),
    ),
}


def _make_contract(name: str, category: str, owner: str, implementation: str) -> EWToolContract:
    access: Literal["read", "write", "provider"] = (
        "provider" if implementation == "external_adapter"
        else "read" if name in _READONLY_PUBLIC_TOOLS
        else "write"
    )
    input_mode: Literal["explicit", "envelope"] = (
        "envelope" if owner == "EWToolSpace" or name in _ENVELOPE_TOOLS else "explicit"
    )
    required = (
        _EXPLICIT_REQUIRED_FIELDS.get(name, ())
        if input_mode == "explicit"
        else _GENERIC_REQUIRED_FIELDS.get(name, ())
    )
    optional = (
        _ENVELOPE_OPTIONAL_FIELDS.get(name, ())
        if input_mode == "envelope"
        else _EXPLICIT_OPTIONAL_FIELDS.get(name, ())
    )
    permission = "public read" if access == "read" else (
        "configured provider boundary" if access == "provider" else "acting agent; domain owner rules apply"
    )
    state_effect = (
        "records a bounded read audit; does not mutate domain state"
        if access == "read"
        else "queues a provider request; never fabricates an external result"
        if access == "provider"
        else "mutates the owner environment and emits a replay/audit event"
    )
    idempotency = "not applicable to read" if access == "read" else "same-step + same-arguments deduplicated"
    audit_event = f"{name}.{'read' if access == 'read' else 'provider_request' if access == 'provider' else 'write'}"
    return EWToolContract(
        input_mode=input_mode,
        actor_field=_ACTOR_FIELDS.get(name, _DEFAULT_ACTOR_FIELD),
        access=access,
        required_fields=required,
        optional_fields=optional,
        permission=permission,
        state_effect=state_effect,
        idempotency=idempotency,
        audit_event=audit_event,
    )


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
            else "generic_contract_tested"
            if name not in _SPECIALIZED_OWNERS
            else "contract_and_unit_tested"
        ),
        contract=_make_contract(
            name,
            category,
            _SPECIALIZED_OWNERS.get(name, "EWToolSpace"),
            (
                "external_adapter"
                if name in _EXTERNAL_PROVIDER_TOOLS
                else "specialized"
                if name in _SPECIALIZED_OWNERS
                else "generic_local"
            ),
        ),
    )
    for category, names in EW_TOOLS_BY_CATEGORY.items()
    for name in names
)
EW_TOOL_SPEC_BY_NAME = {spec.name: spec for spec in EW_TOOL_SPECS}


def tool_catalog_rows() -> list[dict]:
    """Return JSON-serializable rows for reports, APIs, and progress dashboards."""
    return [asdict(spec) for spec in EW_TOOL_SPECS]


def tool_contract_rows() -> list[dict]:
    """Return the behavioral B1 contract layer as JSON-serializable rows."""
    rows = []
    for spec in EW_TOOL_SPECS:
        contract = spec.contract
        rows.append({
            "name": spec.name,
            "category": spec.category,
            "owner": spec.owner,
            "input_mode": contract.input_mode,
            "actor_field": contract.actor_field.name,
            "access": contract.access,
            "required_fields": [field.name for field in contract.required_fields],
            "optional_fields": [field.name for field in contract.optional_fields],
            "permission": contract.permission,
            "state_effect": contract.state_effect,
            "idempotency": contract.idempotency,
            "audit_event": contract.audit_event,
        })
    return rows


def _validate_field_value(field: EWToolField, value, path: str) -> str | None:
    """Return a stable error for one value in a contract payload."""
    if value is None:
        return None
    if field.type == "integer":
        try:
            if isinstance(value, bool):
                raise ValueError
            int(value)
        except (TypeError, ValueError):
            return f"{path} must be an integer"
    elif field.type == "number":
        try:
            if isinstance(value, bool):
                raise ValueError
            float(value)
        except (TypeError, ValueError):
            return f"{path} must be a number"
    elif field.type == "object" and not isinstance(value, dict):
        return f"{path} must be an object"
    elif field.type == "array" and not isinstance(value, list):
        return f"{path} must be an array"
    elif field.type == "boolean" and not isinstance(value, bool):
        return f"{path} must be a boolean"
    elif field.type == "string" and not isinstance(value, str):
        return f"{path} must be a string"
    elif field.type == "string_or_object" and not isinstance(value, (str, dict, list)):
        return f"{path} must be a string or structured value"
    return None


def _validate_payload_fields(
    contract: EWToolContract,
    payload: dict,
    prefix: str,
) -> tuple[bool, str | None]:
    for field in contract.required_fields:
        value = payload.get(field.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, f"{prefix}.{field.name} is required"
        error = _validate_field_value(field, value, f"{prefix}.{field.name}")
        if error:
            return False, error
    for field in contract.optional_fields:
        if field.name not in payload or payload[field.name] is None:
            continue
        error = _validate_field_value(field, payload[field.name], f"{prefix}.{field.name}")
        if error:
            return False, error
    return True, None


def validate_tool_request(name: str, request: dict | None) -> tuple[bool, str | None]:
    """Validate a tool's business payload.

    For an ``envelope`` tool, ``request`` is the nested request dictionary.
    For an ``explicit`` tool, ``request`` is the business-argument dictionary
    without the actor field.  The actor is already a separate argument in the
    environment dispatch path.  ``validate_tool_arguments`` validates the
    complete top-level LLM tool-call payload, including that actor field.
    """
    if name not in EW_TOOL_SPEC_BY_NAME:
        return False, f"unknown public EW tool: {name}"
    if request is None:
        request = {}
    if not isinstance(request, dict):
        return False, "request must be an object"
    contract = EW_TOOL_SPEC_BY_NAME[name].contract
    return _validate_payload_fields(contract, request, "request")


def validate_tool_arguments(name: str, arguments: dict | None) -> tuple[bool, str | None]:
    """Validate the complete argument object emitted by an LLM tool call.

    This is deliberately a contract-level check, not a replacement for each
    domain environment's permission and state-machine validation.  It catches
    the most damaging drift: a model-facing schema that omits the actor,
    misses a required business field, or sends a value with the wrong JSON
    shape.  Envelope tools validate their nested ``request`` payload; explicit
    tools validate business fields at the top level.
    """
    if name not in EW_TOOL_SPEC_BY_NAME:
        return False, f"unknown public EW tool: {name}"
    if not isinstance(arguments, dict):
        return False, "arguments must be an object"
    contract = EW_TOOL_SPEC_BY_NAME[name].contract
    actor = contract.actor_field
    if actor.name not in arguments or arguments[actor.name] is None:
        return False, f"arguments.{actor.name} is required"
    actor_error = _validate_field_value(actor, arguments[actor.name], f"arguments.{actor.name}")
    if actor_error:
        return False, actor_error
    if contract.input_mode == "envelope":
        nested = arguments.get("request")
        if nested is None:
            nested = {}
        if not isinstance(nested, dict):
            return False, "arguments.request must be an object"
        valid, reason = _validate_payload_fields(contract, nested, "arguments.request")
        return valid, reason
    payload = {key: value for key, value in arguments.items() if key != actor.name}
    return _validate_payload_fields(contract, payload, "arguments")


def render_tool_contract_markdown() -> str:
    """Render the machine-readable contract layer for design review."""
    lines = [
        "<!-- Generated from EW_TOOL_SPECS.contract; do not hand-edit. -->",
        "",
        "| 工具 | owner | 输入模式 | 主体字段 | 读写 | 必填字段 | 可选字段 | 权限 | 状态影响 | 审计事件 | 幂等 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for spec in EW_TOOL_SPECS:
        contract = spec.contract
        required = ", ".join(field.name for field in contract.required_fields) or "—"
        optional = ", ".join(field.name for field in contract.optional_fields) or "—"
        lines.append(
            "| `{}` | `{}` | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                spec.name,
                spec.owner,
                contract.input_mode,
                contract.actor_field.name,
                contract.access,
                required,
                optional,
                contract.permission,
                contract.state_effect,
                contract.audit_event,
                contract.idempotency,
            )
        )
    return "\n".join(lines) + "\n"


def render_tool_catalog_markdown() -> str:
    """Render all public tools for a human review or project progress report."""
    labels = {
        "specialized": "专用实现",
        "generic_local": "本地通用实现",
        "external_adapter": "外部能力适配器",
        "contract_and_unit_tested": "契约与单元测试通过",
        "generic_contract_tested": "通用契约测试通过，领域语义待验收",
        "registered_and_router_tested": "注册与路由验证通过，尚缺独立行为测试",
        "provider_boundary_only": "仅适配边界通过，需接入真实服务验证",
    }
    lines = [
        "<!-- Generated from EW_TOOL_SPECS; the surrounding document supplies the heading. -->",
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
