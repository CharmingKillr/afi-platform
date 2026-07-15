"""Authoritative public EW tool catalog used by B1 coverage checks.

Source: EmergenceAI/Emergence-World ``tools/README.md`` (2026-07-15).
The public table currently contains 113 unique names although the project
describes the evolving private/runtime catalog as "120+".
"""
from __future__ import annotations

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
