"""LandmarkSpace — EW landmarks as an AS custom env (lightweight).

A2 ships a small set of named EW landmarks (BookWorm / Ad Tower / Agent
Billboard / Town Hall / Victory Arch) as readable text the agents can list
and inspect. No coordinates, no map, no pyproj/Pillow — that's A4
(MobilitySpace). This keeps the EW subset runnable with stdlib + AS only.

The landmark data is injected via init_config kwargs by ``afi.world.scenario``
(landmarks: list[dict]); a minimal inline default keeps the env importable
standalone. Like governance_space.py, this module runs in the AS venv so it
depends ONLY on agentsociety2 + stdlib.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, List

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from mcp.server.fastmcp.tools.tool_manager import ToolManager

_logger = get_logger()


def _parse_pic001_call(
    instruction: str,
    available_tool_names: set[str],
    tool_objects: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Parse one explicit PIC-001 call without evaluating arbitrary code.

    Contract checkpoints use a deliberately small Python-call notation, for
    example ``Call read_blog(agent_id=2, blog_id=1)``.  The old route sent this
    text back through free-form Python code generation.  ``ast.literal_eval``
    lets us retain familiar argument syntax while rejecting expressions,
    attributes, imports, and other executable payloads.

    Positional arguments are normalized against the registered tool function's
    signature so the router still invokes tools with keyword arguments.
    Natural-language instructions and malformed explicit calls return ``None``
    and continue through the normal LLM codegen path.
    """
    text = str(instruction).strip()
    if text.startswith("Call "):
        text = text[5:].strip()
    if text.endswith("."):
        text = text[:-1].rstrip()
    try:
        expression = ast.parse(text, mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
        return None
    tool_name = expression.func.id
    if tool_name not in available_tool_names:
        return None
    if any(keyword.arg is None for keyword in expression.keywords):
        return None

    try:
        values = [ast.literal_eval(arg) for arg in expression.args]
        values_by_name = {
            str(keyword.arg): ast.literal_eval(keyword.value)
            for keyword in expression.keywords
        }
    except (ValueError, TypeError, SyntaxError):
        return None

    if values:
        if tool_objects is None or tool_name not in tool_objects:
            return None
        function = getattr(tool_objects[tool_name], "fn", None)
        if function is None:
            return None
        try:
            parameters = list(inspect.signature(function).parameters.values())
        except (TypeError, ValueError):
            return None
        positional_names = [
            parameter.name
            for parameter in parameters
            if parameter.name not in {"self", "cls"}
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        ]
        if len(values) > len(positional_names):
            return None
        for name, value in zip(positional_names, values, strict=False):
            if name in values_by_name:
                return None
            values_by_name[name] = value
    return tool_name, values_by_name


def _append_pic001_router_record(router: Any, record: dict[str, Any]) -> None:
    """Persist one structured call for replay/audit without changing AS files."""
    run_dir = getattr(router, "run_dir", None)
    if not run_dir:
        return
    try:
        artifacts = Path(run_dir) / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        path = artifacts / "pic001_structured_call_log.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        _logger.debug("Unable to persist PIC-001 structured call record", exc_info=True)


def _pic001_structured_mode_enabled() -> bool:
    """Return whether PIC-001 should use native function calling.

    The switch is intentionally environment-scoped.  AgentSociety's router is
    shared by all environments in a run, so changing the upstream router
    globally would silently change unrelated scenarios.  The default remains
    ``codegen`` for backwards compatibility; PIC-001 opts in from its local
    ``.env`` file.
    """
    return os.environ.get("AFI_PIC001_ROUTER_MODE", "codegen").strip().lower() == "structured"


def _pic001_structured_call_limit() -> int:
    """Read the bounded number of native tool calls allowed for one ask."""
    raw_limit = os.environ.get("AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS", "3")
    try:
        return max(1, int(raw_limit))
    except (TypeError, ValueError):
        _logger.warning(
            "Invalid AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS=%r; using 3",
            raw_limit,
        )
        return 3


def _pic001_structured_max_tokens() -> int:
    """Bound native tool-call responses so local reasoning cannot run away."""
    raw_limit = os.environ.get("AFI_PIC001_STRUCTURED_MAX_TOKENS", "512")
    try:
        return max(64, int(raw_limit))
    except (TypeError, ValueError):
        _logger.warning(
            "Invalid AFI_PIC001_STRUCTURED_MAX_TOKENS=%r; using 512",
            raw_limit,
        )
        return 512


def _pic001_disable_thinking() -> bool:
    """Read the local-vLLM switch for concise structured tool selection."""
    return os.environ.get("AFI_PIC001_DISABLE_THINKING", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


_PIC001_TOOL_GROUPS: dict[str, frozenset[str]] = {
    # The core observation group is deliberately small.  In the previous run,
    # a generic <observe> request exposed every readonly tool and the model
    # frequently returned a batch of unrelated reads in one response.
    "observe_core": frozenset(
        {
            "list_landmarks",
            "read_agent_manifesto",
            "read_constitution",
            "list_blogs",
            "read_billboard",
            "read_messages",
            "list_proposals",
            "list_credit_pitches",
        }
    ),
    "social": frozenset({"send_message", "read_messages"}),
    "evidence": frozenset(
        {
            "list_blogs",
            "read_blog",
            "write_blog",
            "update_blog",
            "delete_blog",
            "comment_on_blog",
        }
    ),
    "broadcast": frozenset(
        {
            "read_billboard",
            "add_to_billboard",
            "reply_to_billboard",
            "react_to_billboard",
        }
    ),
    "governance": frozenset(
        {
            "read_constitution",
            "list_proposals",
            "read_townhall_proposal",
            "submit_townhall_proposal",
            "comment_on_proposal",
            "update_proposal",
            "vote_on_proposal",
            "submit_final_report",
        }
    ),
    "economy": frozenset(
        {"list_credit_pitches", "submit_grant_pitch", "vote_for_pitch"}
    ),
    "trust": frozenset(
        {
            "check_agent_trust",
            "rate_agent_trust",
            "tool_usage_analytics_by_character",
        }
    ),
    "discovery": frozenset(
        {"list_landmarks", "read_agent_manifesto", "browse_tool_registry"}
    ),
}

_PIC001_SCOPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "social": ("message", "mailbox", "private", "dm", "私信", "消息"),
    "evidence": (
        "blog",
        "evidence",
        "claim",
        "verify",
        "verification",
        "证据",
        "核验",
        "博客",
        "文章",
    ),
    "broadcast": (
        "billboard",
        "public",
        "broadcast",
        "post",
        "reply",
        "react",
        "公告",
        "传播",
        "公开",
    ),
    "governance": (
        "town hall",
        "proposal",
        "constitution",
        "vote",
        "governance",
        "治理",
        "提案",
        "投票",
        "宪法",
    ),
    "economy": (
        "pitch",
        "grant",
        "credit",
        "economy",
        "奖励",
        "积分",
        "资助",
    ),
    "trust": ("trust", "report", "analytics", "信任", "报告", "统计"),
    "discovery": (
        "landmark",
        "registry",
        "manifesto",
        "环境",
        "地标",
        "工具目录",
        "宣言",
    ),
}


def _pic001_select_structured_tools(
    instruction: str,
    readonly: bool,
    available_names: set[str],
) -> tuple[set[str], str]:
    """Select a bounded tool surface for one PIC-001 native-call request.

    ``all`` remains the backwards-compatible default.  The local PIC-001
    config uses ``staged``: readonly requests receive the core observation
    surface plus at most two semantically matched groups, while mutation
    requests with explicit domain language receive the matching groups.  A
    mutation request without a recognizable domain stays on the full surface
    so this guard does not silently turn a valid user task into a no-op.
    """
    raw_scope = os.environ.get("AFI_PIC001_STRUCTURED_TOOL_SCOPE", "all")
    scope = raw_scope.strip().lower()
    available = set(available_names)
    if scope in {"", "all", "*"}:
        return available, "all"

    if scope in {"staged", "auto"}:
        text = str(instruction).lower()
        matched = [
            group
            for group, keywords in _PIC001_SCOPE_KEYWORDS.items()
            if any(keyword in text for keyword in keywords)
        ]
        if readonly:
            # Always retain the stable cross-domain index.  Add at most two
            # relevant groups so a request about proposals does not expose
            # social, economy, trust, and registry tools simultaneously.
            groups = ["observe_core", *matched[:2]]
            label = "staged:" + "+".join(groups)
        elif matched:
            groups = matched[:2]
            label = "staged:" + "+".join(groups)
        else:
            return available, "staged:all_for_unclassified_mutation"
        selected = set().union(*(set(_PIC001_TOOL_GROUPS[group]) for group in groups))
        return selected & available, label

    requested = [item.strip() for item in re.split(r"[,; ]+", scope) if item.strip()]
    selected: set[str] = set()
    for item in requested:
        selected.update(_PIC001_TOOL_GROUPS.get(item, {item}))
    selected &= available
    if selected:
        return selected, "explicit:" + "+".join(requested)
    _logger.warning(
        "AFI_PIC001_STRUCTURED_TOOL_SCOPE=%r selected no active tools; using all",
        raw_scope,
    )
    return available, "all_invalid_scope_fallback"


def _pic001_get_field(value: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a dict or an SDK/Pydantic response object."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _pic001_tool_call_payload(tool_call: Any) -> dict[str, Any]:
    """Normalize an OpenAI-compatible tool-call object to plain dictionaries."""
    function = _pic001_get_field(tool_call, "function", {}) or {}
    return {
        "id": _pic001_get_field(tool_call, "id", "pic001-call"),
        "type": _pic001_get_field(tool_call, "type", "function"),
        "function": {
            "name": _pic001_get_field(function, "name", ""),
            "arguments": _pic001_get_field(function, "arguments", "{}"),
        },
    }


def _pic001_validate_tool_arguments(
    tool_schema: dict[str, Any], arguments: Any
) -> str | None:
    """Validate native-call arguments against the registered JSON Schema.

    Tool functions still perform their own domain checks.  This layer catches
    malformed argument shapes, missing required fields, wrong primitive types,
    and enum violations before a state-changing function is invoked.
    """
    if not isinstance(arguments, dict):
        return "tool arguments must be a JSON object"

    parameters = (
        tool_schema.get("function", {}).get("parameters", {})
        if isinstance(tool_schema, dict)
        else {}
    )
    if not parameters:
        return None

    try:
        from jsonschema import Draft7Validator

        errors = sorted(
            Draft7Validator(parameters).iter_errors(arguments),
            key=lambda error: list(error.path),
        )
    except Exception as exc:
        # A missing optional jsonschema dependency must not disable the custom
        # module.  Required-field checking remains useful as a conservative
        # fallback; the normal tool function is the final domain validator.
        required = parameters.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            return f"missing required argument(s): {', '.join(missing)}"
        _logger.debug("PIC-001 JSON Schema validation unavailable: %s", exc)
        return None

    if errors:
        return "; ".join(error.message for error in errors[:3])
    return None


def _pic001_structured_prompt(
    ctx: dict[str, Any], instruction: str, readonly: bool, tool_scope: str
) -> str:
    """Build the user message for native tool calling, with no Python surface."""
    readonly_note = (
        "You are in READONLY mode. You may call only readonly tools."
        if readonly
        else "You may call both readonly and state-changing tools when required."
    )
    return f"""You are an agent operating inside a virtual-world simulation.

The task is described below. Use the provided native function tools to act on
the simulation. Do not write Python, do not emit a Call(...) expression, and do
not invent a tool name. If the task does not require a tool, answer briefly in
plain text.

{readonly_note}
Tool exposure scope for this request: {tool_scope}
Only choose from the tools actually provided in this request. Prefer one
minimal tool call that advances the task; do not batch unrelated observations.

Current simulation time: {getattr(ctx, 'current_time', None) if not isinstance(ctx, dict) else ctx.get('current_time', '')}
Agent context:
{json.dumps(ctx, ensure_ascii=False, default=str)}

Task:
{instruction}
"""


def _patch_empty_codegen_buckets() -> None:
    """Avoid an unnecessary AS 2.7.0 LLM call for empty observe buckets.

    AgentSociety 2.7.0 always materializes ``(readonly, kind)`` entries in
    ``CodeGenRouter._tools_pyi_dict``.  Its ``init()`` then checks only for the
    key, so a scenario with no observe/statistics tools still asks the LLM to
    synthesize an empty program before step 0.  That is particularly brittle
    for local coding models and is unrelated to PIC-001's public-tool test.

    The patch is deliberately narrow: it removes only buckets whose generated
    description says that no environment modules are available.  Non-empty
    observe/statistics buckets retain AgentSociety's normal behavior.
    """
    try:
        from agentsociety2.env.router_codegen import CodeGenRouter

        if getattr(CodeGenRouter, "_afi_empty_codegen_patch", False):
            return

        original_init = CodeGenRouter.init

        async def _init_without_empty_codegen(self, start_datetime):
            buckets = getattr(self, "_tools_pyi_dict", {})
            for key in ((True, "observe"), (True, "statistics")):
                description = buckets.get(key, "")
                if "# No environment modules" in description:
                    buckets.pop(key, None)
            return await original_init(self, start_datetime)

        CodeGenRouter.init = _init_without_empty_codegen
        CodeGenRouter._afi_empty_codegen_patch = True
    except Exception:
        # The module must remain importable by the AS custom-module scanner even
        # when a different backend is inspecting it without AgentSociety2.
        return


_patch_empty_codegen_buckets()


def _patch_explicit_pic001_plans() -> None:
    """Execute PIC-001's explicit Call checkpoints without lossy replanning.

    The AS helper is designed for free-form requests and asks a planning LLM to
    convert every intervention into a JSON plan.  PIC-001 is different: its
    intervention text is already a versioned, ordered tool contract.  With a
    local model, the generic planner can legally return an ``ask_environment``
    step whose ``question`` is empty, which makes a valid checkpoint fail before
    the environment router sees the requested tool.

    For instructions containing explicit ``Call tool(...)`` entries, convert
    those entries directly into the helper's normal PlanStep objects.  The
    resulting steps still go through ``ask_environment`` and therefore still
    exercise the model-backed CodeGenRouter and the real tool implementation.
    Non-scripted asks/interventions continue to use AgentSociety's original
    planner.
    """
    try:
        from agentsociety2.society.helper import AgentSocietyHelper, PlanStep

        if getattr(AgentSocietyHelper, "_afi_pic001_plan_patch", False):
            return

        original_create_plan = AgentSocietyHelper._create_plan
        original_replan = AgentSocietyHelper._replan
        original_final_answer = AgentSocietyHelper._generate_final_answer

        def _extract_calls(task: str) -> list[str]:
            calls: list[str] = []
            pattern = re.compile(
                r"Call\s+([A-Za-z_][A-Za-z0-9_]*\([^\"]*\))",
                flags=re.DOTALL,
            )
            for match in pattern.finditer(task):
                call = match.group(0).strip().rstrip(".")
                if call not in calls:
                    calls.append(call)
            return calls

        async def _create_plan(self, task, readonly):
            self._afi_explicit_plan = False
            if not readonly:
                calls = _extract_calls(str(task))
                if calls:
                    self._afi_explicit_plan = True
                    # The scenario's contract can contain more than the
                    # helper's default eight steps (PIC-001 baseline has nine).
                    self._max_steps = max(self._max_steps, len(calls))
                    self._max_replans = max(self._max_replans, len(calls) * 2)
                    return [
                        PlanStep(
                            description=f"Execute explicit environment call: {call}",
                            tool="ask_environment",
                            args={"question": call},
                            expected_output="The requested PIC-001 tool result.",
                        )
                        for call in calls
                    ]
            return await original_create_plan(self, task, readonly)

        async def _replan(self, original_task, current_plan, execution_history, readonly):
            if getattr(self, "_afi_explicit_plan", False):
                # Keep the original ordered contract; _run() advances by the
                # execution-history length and will move to the next call.
                return current_plan
            return await original_replan(
                self, original_task, current_plan, execution_history, readonly
            )

        async def _generate_final_answer(self, task, plan, execution_history, readonly):
            if getattr(self, "_afi_explicit_plan", False):
                success_count = sum(
                    1 for entry in execution_history if entry.get("success")
                )
                return (
                    f"Executed {success_count}/{len(execution_history)} explicit "
                    "PIC-001 environment calls."
                )
            return await original_final_answer(
                self, task, plan, execution_history, readonly
            )

        AgentSocietyHelper._create_plan = _create_plan
        AgentSocietyHelper._replan = _replan
        AgentSocietyHelper._generate_final_answer = _generate_final_answer
        AgentSocietyHelper._afi_pic001_plan_patch = True
    except Exception:
        # Keep custom-module discovery usable outside an AgentSociety runtime.
        return


def _patch_explicit_pic001_codegen_router() -> None:
    """Add a schema-checked direct route for Contract Mode checkpoints.

    ``ask_environment`` is intentionally retained as the public boundary, but
    an explicit PIC-001 call must not be translated into free-form Python.  The
    direct route is narrow: it activates only for a single literal ``Call ...``
    instruction and only for a registered tool in the current router.  All
    ordinary agent requests continue through CodeGenRouter's LLM path, so this
    patch separates tool-contract validation from autonomy experiments rather
    than disabling LLM behavior globally.
    """
    try:
        from agentsociety2.env.router_codegen import CodeGenRouter

        if getattr(CodeGenRouter, "_afi_pic001_structured_patch", False):
            return

        original_init = CodeGenRouter.__init__
        original_ask = CodeGenRouter.ask

        def _init(self, *args, **kwargs):
            # The upstream default is ten code-generation retries.  That is
            # reasonable for a remote high-reliability provider, but it turns
            # one malformed autonomous call into a multi-minute stall for a
            # local model.  Keep the bound configurable and leave the upstream
            # default untouched outside this scenario.
            raw_limit = os.environ.get("AFI_PIC001_CODEGEN_MAX_RETRIES")
            if raw_limit:
                try:
                    limit = max(1, int(raw_limit))
                    if "max_llm_call_retry" in kwargs:
                        kwargs["max_llm_call_retry"] = min(
                            int(kwargs["max_llm_call_retry"]), limit
                        )
                    elif len(args) >= 4:
                        args = list(args)
                        args[3] = min(int(args[3]), limit)
                        args = tuple(args)
                    else:
                        kwargs["max_llm_call_retry"] = limit
                except (TypeError, ValueError):
                    _logger.warning("Invalid AFI_PIC001_CODEGEN_MAX_RETRIES=%r", raw_limit)
            return original_init(self, *args, **kwargs)

        async def _structured_ask(
            self,
            ctx,
            instruction,
            readonly=False,
            template_mode=False,
            trace_id=None,
            parent_span_id=None,
        ):
            """Execute native function calls with a bounded, auditable loop."""
            registered: dict[str, Any] = {}
            all_available_tools: list[dict[str, Any]] = []
            all_available_names: set[str] = set()
            for module in getattr(self, "env_modules", []):
                registered.update(getattr(module.__class__, "_registered_tools", {}))
                module_tools = (
                    getattr(module, "_readonly_llm_tools", [])
                    if readonly
                    else getattr(module, "_llm_tools", [])
                )
                for schema in module_tools:
                    name = _pic001_get_field(
                        _pic001_get_field(schema, "function", {}), "name", ""
                    )
                    if name and name in registered and name not in all_available_names:
                        all_available_tools.append(schema)
                        all_available_names.add(name)

            available_names, tool_scope = _pic001_select_structured_tools(
                str(instruction), readonly, all_available_names
            )
            available_tools = [
                schema
                for schema in all_available_tools
                if _pic001_get_field(
                    _pic001_get_field(schema, "function", {}), "name", ""
                )
                in available_names
            ]

            if not available_tools:
                result = {
                    "status": "fail",
                    "error": "structured_no_available_tools",
                }
                _append_pic001_router_record(
                    self,
                    {
                        "mode": "structured_autonomy",
                        "instruction": str(instruction),
                        "readonly": readonly,
                        "tool_scope": tool_scope,
                        "status": "fail",
                        "error": result["error"],
                    },
                )
                return result, result["error"]

            max_tool_calls = _pic001_structured_call_limit()
            messages: list[dict[str, Any]] = [
                {
                        "role": "user",
                        "content": _pic001_structured_prompt(
                            ctx if isinstance(ctx, dict) else {},
                            str(instruction),
                            readonly,
                            tool_scope,
                        ),
                    }
                ]
            call_records: list[dict[str, Any]] = []
            results: dict[str, Any] = {
                "status": "no_tool_call",
                "tool_calls": call_records,
            }
            total_tool_calls = 0

            self.set_trace_context(trace_id, parent_span_id)
            trace_token = self._set_trace_context(
                trace_id,
                parent_span_id,
                ctx.get("agent_id") if isinstance(ctx, dict) else None,
            )
            try:
                for turn in range(1, max_tool_calls + 1):
                    try:
                        completion_kwargs: dict[str, Any] = {
                            "model": "coder",
                            "messages": messages,
                            "tools": available_tools,
                            "tool_choice": "auto",
                            "max_retries": 1,
                            "max_tokens": _pic001_structured_max_tokens(),
                        }
                        if _pic001_disable_thinking():
                            completion_kwargs["chat_template_kwargs"] = {
                                "enable_thinking": False
                            }
                        response = await self.acompletion_with_system_prompt(
                            **completion_kwargs
                        )
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        results.update(
                            {
                                "status": "structured_llm_error",
                                "error": error,
                                "turn": turn,
                            }
                        )
                        _append_pic001_router_record(
                            self,
                            {
                                "mode": "structured_autonomy",
                                "instruction": str(instruction),
                                "readonly": readonly,
                                "tool_scope": tool_scope,
                                "status": "structured_llm_error",
                                "error": error,
                                "turn": turn,
                            },
                        )
                        return results, error

                    message = _pic001_get_field(
                        _pic001_get_field(response, "choices", [])[0],
                        "message",
                        {},
                    )
                    raw_tool_calls = _pic001_get_field(message, "tool_calls", None) or []
                    content = _pic001_get_field(message, "content", "") or ""
                    if not raw_tool_calls:
                        results["status"] = "success" if call_records else "no_tool_call"
                        results["answer"] = str(content)
                        return results, str(content)

                    normalized_calls = [
                        _pic001_tool_call_payload(tool_call)
                        for tool_call in raw_tool_calls
                    ]
                    messages.append(
                        {
                            "role": "assistant",
                            "content": content or None,
                            "tool_calls": normalized_calls,
                        }
                    )
                    tool_messages: list[dict[str, Any]] = []

                    for tool_call in normalized_calls:
                        call_id = tool_call["id"]
                        function_payload = tool_call["function"]
                        tool_name = str(function_payload.get("name", ""))
                        raw_arguments = function_payload.get("arguments", "{}")

                        if total_tool_calls >= max_tool_calls:
                            truncated = {
                                "mode": "structured_autonomy",
                                "instruction": str(instruction),
                                "readonly": readonly,
                                "tool_scope": tool_scope,
                                "tool": tool_name,
                                "status": "max_tool_calls_reached",
                                "turn": turn,
                                "error": f"maximum of {max_tool_calls} tool calls reached",
                            }
                            call_records.append(truncated)
                            _append_pic001_router_record(self, truncated)
                            continue

                        total_tool_calls += 1
                        record: dict[str, Any] = {
                            "mode": "structured_autonomy",
                            "instruction": str(instruction),
                            "readonly": readonly,
                            "tool_scope": tool_scope,
                            "tool": tool_name,
                            "turn": turn,
                            "call_index": total_tool_calls,
                        }

                        if tool_name not in available_names:
                            readonly_violation = readonly and tool_name in registered
                            error = (
                                f"tool {tool_name} is not readonly"
                                if readonly_violation
                                else f"tool {tool_name} is not available in this mode"
                            )
                            record.update(
                                {
                                    "status": (
                                        "readonly_tool_violation"
                                        if readonly_violation
                                        else "tool_not_allowed"
                                    ),
                                    "error": error,
                                }
                            )
                            call_records.append(record)
                            _append_pic001_router_record(self, record)
                            results.update(
                                {
                                    "status": "fail",
                                    "error": record["error"],
                                }
                            )
                            return results, record["error"]

                        try:
                            arguments = json.loads(str(raw_arguments))
                        except (TypeError, ValueError, json.JSONDecodeError) as exc:
                            record.update(
                                {
                                    "status": "structured_parse_error",
                                    "error": f"invalid JSON arguments: {exc}",
                                }
                            )
                            call_records.append(record)
                            _append_pic001_router_record(self, record)
                            results.update(
                                {
                                    "status": "structured_parse_error",
                                    "error": record["error"],
                                }
                            )
                            return results, record["error"]

                        schema = next(
                            (
                                item
                                for item in available_tools
                                if _pic001_get_field(
                                    _pic001_get_field(item, "function", {}),
                                    "name",
                                    "",
                                )
                                == tool_name
                            ),
                            {},
                        )
                        schema_error = _pic001_validate_tool_arguments(schema, arguments)
                        if schema_error:
                            record.update(
                                {
                                    "status": "structured_schema_error",
                                    "args": arguments,
                                    "error": schema_error,
                                }
                            )
                            call_records.append(record)
                            _append_pic001_router_record(self, record)
                            results.update(
                                {
                                    "status": "structured_schema_error",
                                    "error": schema_error,
                                }
                            )
                            return results, schema_error

                        module = next(
                            (
                                candidate
                                for candidate in getattr(self, "env_modules", [])
                                if tool_name
                                in getattr(candidate.__class__, "_registered_tools", {})
                            ),
                            None,
                        )
                        tool_object = registered.get(tool_name)
                        function = getattr(tool_object, "fn", None)
                        if module is None or function is None:
                            error = f"tool {tool_name} is not routable"
                            record.update(
                                {
                                    "status": "structured_route_error",
                                    "args": arguments,
                                    "error": error,
                                }
                            )
                            call_records.append(record)
                            _append_pic001_router_record(self, record)
                            results.update({"status": "fail", "error": error})
                            return results, error

                        try:
                            async with self._exec_lock_ctx():
                                value = function(module, **arguments)
                                if inspect.isawaitable(value):
                                    value = await value
                            tool_result = (
                                dict(value) if isinstance(value, dict) else {"value": value}
                            )
                            tool_result.setdefault("status", "success")
                            tool_status = str(tool_result.get("status", "success"))
                            record.update(
                                {
                                    "status": tool_status,
                                    "args": arguments,
                                    "result": tool_result,
                                    "simulation_time": str(getattr(self, "t", "")),
                                }
                            )
                            call_records.append(record)
                            _append_pic001_router_record(self, record)
                            results[tool_name] = tool_result
                            results["status"] = (
                                "success" if tool_status not in {"fail", "error"} else tool_status
                            )
                            tool_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": tool_name,
                                    "content": json.dumps(
                                        tool_result,
                                        ensure_ascii=False,
                                        default=str,
                                    ),
                                }
                            )
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                            record.update(
                                {
                                    "status": "error",
                                    "args": arguments,
                                    "error": error,
                                }
                            )
                            call_records.append(record)
                            _append_pic001_router_record(self, record)
                            results.update({"status": "error", "error": error})
                            tool_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": tool_name,
                                    "content": json.dumps(
                                        {"status": "error", "error": error},
                                        ensure_ascii=False,
                                    ),
                                }
                            )

                    if tool_messages:
                        messages.extend(tool_messages)
                    if total_tool_calls >= max_tool_calls:
                        results["status"] = "max_tool_calls_reached"
                        results["error"] = (
                            f"maximum of {max_tool_calls} structured tool calls reached"
                        )
                        return results, results["error"]

                results["status"] = "max_tool_calls_reached"
                results["error"] = (
                    f"maximum of {max_tool_calls} structured tool calls reached"
                )
                return results, results["error"]
            finally:
                self._reset_trace_context(trace_token)
                self.clear_trace_context()

        async def _ask(self, ctx, instruction, readonly=False, template_mode=False,
                       trace_id=None, parent_span_id=None):
            registered: dict[str, Any] = {}
            for module in getattr(self, "env_modules", []):
                registered.update(getattr(module.__class__, "_registered_tools", {}))
            parsed = _parse_pic001_call(
                instruction,
                set(registered),
                registered,
            )
            if parsed is None:
                if _pic001_structured_mode_enabled():
                    return await _structured_ask(
                        self,
                        ctx,
                        instruction,
                        readonly,
                        template_mode,
                        trace_id,
                        parent_span_id,
                    )
                return await original_ask(
                    self, ctx, instruction, readonly, template_mode,
                    trace_id, parent_span_id,
                )

            tool_name, arguments = parsed
            readonly_tools = {
                name
                for module in getattr(self, "env_modules", [])
                for name, is_readonly in getattr(module.__class__, "_readonly_tools", {}).items()
                if is_readonly
            }
            if readonly and tool_name not in readonly_tools:
                result = {
                    "status": "fail",
                    "error": f"tool {tool_name} is not readonly",
                }
                _append_pic001_router_record(self, {
                    "mode": "contract",
                    "instruction": str(instruction),
                    "tool": tool_name,
                    "args": arguments,
                    "status": "fail",
                    "error": result["error"],
                })
                return result, result["error"]

            module = next(
                (
                    candidate
                    for candidate in getattr(self, "env_modules", [])
                    if tool_name in getattr(candidate.__class__, "_registered_tools", {})
                ),
                None,
            )
            tool_object = registered[tool_name]
            function = getattr(tool_object, "fn", None)
            if module is None or function is None:
                result = {"status": "fail", "error": f"tool {tool_name} is not routable"}
                _append_pic001_router_record(self, {
                    "mode": "contract",
                    "instruction": str(instruction),
                    "tool": tool_name,
                    "args": arguments,
                    "status": "fail",
                    "error": result["error"],
                })
                return result, result["error"]

            self.set_trace_context(trace_id, parent_span_id)
            trace_token = self._set_trace_context(
                trace_id,
                parent_span_id,
                ctx.get("agent_id") if isinstance(ctx, dict) else None,
            )
            try:
                async with self._exec_lock_ctx():
                    value = function(module, **arguments)
                    if inspect.isawaitable(value):
                        value = await value
                if isinstance(value, dict):
                    result = dict(value)
                else:
                    result = {"value": value}
                result.setdefault("status", "success")
                status = str(result.get("status", "success"))
                record = {
                    "mode": "contract",
                    "instruction": str(instruction),
                    "tool": tool_name,
                    "args": arguments,
                    "status": status,
                    "result": result,
                    "simulation_time": str(getattr(self, "t", "")),
                }
                _append_pic001_router_record(self, record)
                answer = f"{tool_name} executed with status={status}."
                return result, answer
            except Exception as exc:
                result = {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                _append_pic001_router_record(self, {
                    "mode": "contract",
                    "instruction": str(instruction),
                    "tool": tool_name,
                    "args": arguments,
                    "status": "error",
                    "error": result["error"],
                })
                return result, result["error"]
            finally:
                self._reset_trace_context(trace_token)
                self.clear_trace_context()

        CodeGenRouter.__init__ = _init
        CodeGenRouter.ask = _ask
        CodeGenRouter._afi_pic001_structured_patch = True
    except Exception:
        # Custom module discovery must remain usable outside an AS runtime.
        return


_patch_explicit_pic001_plans()
_patch_explicit_pic001_codegen_router()


class LandmarkSpace(EnvBase):
    """Named EW landmarks agents can list and read about."""

    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("num_landmarks", "INTEGER"),
    ]

    def __init__(self, landmarks: List[dict] | None = None, enabled_tools: List[str] | None = None, **kwargs):
        if kwargs:
            _logger.warning(
                f"LandmarkSpace unknown kwargs ignored: {list(kwargs.keys())}"
            )
        super().__init__()
        if not landmarks:
            landmarks = [
                {
                    "name": "Town Hall",
                    "tagline": "Where the City Decides",
                    "description": "The governance chamber.",
                    "things_to_do": ["Propose / vote on amendments", "Read the live constitution"],
                    "folklore": "Where the Constitution can be changed.",
                }
            ]
        self._landmarks: dict[str, dict] = {lm["name"]: lm for lm in landmarks}
        self._step_counter: int = 0

        registered_names = set(self._registered_tools)
        if enabled_tools is None:
            allowed_tools = registered_names
        else:
            requested_names = [str(name) for name in enabled_tools]
            if len(requested_names) != len(set(requested_names)):
                raise ValueError("enabled_tools must not contain duplicate names")
            requested_tools = set(requested_names)
            unknown_tools = requested_tools - registered_names
            if unknown_tools:
                raise ValueError(f"unknown LandmarkSpace tools: {sorted(unknown_tools)}")
            allowed_tools = requested_tools
        self._enabled_tools = sorted(allowed_tools)
        self._tool_manager = ToolManager(
            tools=[tool_obj for name, tool_obj in self._registered_tools.items() if name in allowed_tools]
        )
        self._llm_tools = [
            item for item in self._llm_tools
            if item["function"]["name"] in allowed_tools
        ]
        self._readonly_llm_tools = [
            item for item in self._readonly_llm_tools
            if item["function"]["name"] in allowed_tools
        ]

    # ── persistence (minimal: no mutable cross-step state worth saving) ──

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        # Landmarks are immutable config; nothing dynamic to persist.

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        return False

    @classmethod
    def description(cls) -> str:
        return "EW named landmarks agents can list and inspect (text only, no map)."

    @classmethod
    def init_description(cls) -> str:
        return """LandmarkSpace: EW landmark catalog (text only, no map).

Agents list named places and read what they can do there. A2 has no spatial
map; this gives agents named destinations (BookWorm, Ad Tower, Agent
Billboard, Town Hall, Victory Arch) without coordinates.

**Initialization Parameters:**
- landmarks (list[dict]): [{name, tagline, description, things_to_do, folklore}]
  Injected by afi.world.scenario. Minimal inline default if omitted.
- enabled_tools (list[str] | None): Optional exact active surface. PIC-001
  exposes only list_landmarks; no coordinates or movement are implied.

**Available tools:**
- list_landmarks(agent_id): all landmark names + taglines (readonly; the
  PIC-001 scenario calls it explicitly during its baseline checkpoint)
- get_landmark_info(agent_id, name): full description of one landmark
"""

    async def step(self, tick: int, t: datetime):
        self.t = t
        self._step_counter += 1
        await self._write_env_state(
            self._step_counter,
            t,
            num_landmarks=len(self._landmarks),
        )

    # ── tools ────────────────────────────────────────────────────────────

    # This is intentionally a normal readonly tool rather than an automatic
    # ``kind="observe"`` hook.  PIC-001 needs to test the explicit
    # ``list_landmarks`` contract at a controlled checkpoint; marking it as an
    # observe hook makes AgentSociety ask the LLM to synthesize an additional
    # observe program during router initialization, before the scenario starts.
    @tool(readonly=True)
    async def list_landmarks(self, agent_id: int) -> dict:
        """List all landmarks with name + tagline.

        :param agent_id: Agent ID
        """
        return {
            "landmarks": [
                {"name": lm["name"], "tagline": lm.get("tagline", "")}
                for lm in self._landmarks.values()
            ],
            "count": len(self._landmarks),
        }

    @tool(readonly=True)
    async def get_landmark_info(self, agent_id: int, name: str) -> dict:
        """Read full info about one landmark.

        :param agent_id: Agent ID
        :param name: landmark name
        """
        lm = self._landmarks.get(name)
        if lm is None:
            return {"error": f"landmark '{name}' not found",
                    "available": list(self._landmarks.keys())}
        return {"landmark": lm}
