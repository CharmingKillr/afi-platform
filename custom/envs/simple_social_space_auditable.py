"""
Social Space Environment
This environment provides social communication functionalities for agents.
"""

import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Tuple

from agentsociety2.env import (
    EnvBase,
    tool,
)
from agentsociety2.env.base import dump_int_map, load_int_map
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text
from mcp.server.fastmcp.tools.tool_manager import ToolManager
from pydantic import BaseModel, Field

# 本模块自选的 workspace 布局：<workspace_root>/state/ENV_STATE.json。
_STATE_REL = "state/ENV_STATE.json"
# [research patch] append-only durable message log (not consumed on read),
# so audit tooling can reconstruct who-said-what even after agents read mail.
_LOG_REL = "state/message_log.jsonl"


class Message(BaseModel):
    """Message model for social space"""

    sender_id: int
    content: str
    timestamp: datetime
    message_id: int  # Unique identifier for each message
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None  # Group ID if this is a group message


class Group(BaseModel):
    """Group model for social space"""

    group_id: int
    name: str
    members: List[int]  # List of agent IDs


# Response models for tool functions
class SendMessageResponse(BaseModel):
    """Response model for send_message() function"""
    status: str = Field("success", description="Operation status")
    sender_id: int = Field(..., description="The ID of the sender agent")
    receiver_id: int = Field(..., description="The ID of the receiver agent")
    content: str = Field(..., description="The content of the message")
    message_id: int | None = Field(None, description="The durable message identifier")
    step: int | None = Field(None, description="Simulation step in which the message was sent")
    deduplicated: bool = Field(False, description="Whether this response came from same-step retry deduplication")
    reason: str | None = Field(None, description="Failure reason, if any")


class ReceiveMessagesResponse(BaseModel):
    """Response model for receive_messages() function"""
    status: str = Field("success", description="Operation status")
    agent_id: int = Field(..., description="The ID of the agent")
    messages: List[dict] = Field(..., description="List of messages received")
    reason: str | None = Field(None, description="Failure reason, if any")


class CreateGroupResponse(BaseModel):
    """Response model for create_group() function"""
    status: str = Field("success", description="Operation status")
    creator_id: int = Field(..., description="The ID of the creator agent")
    group_id: int = Field(..., description="The ID of the created group")
    name: str = Field("", description="The name of the group")
    reason: str | None = Field(None, description="Failure reason, if any")
    deduplicated: bool = Field(False, description="Whether this response came from same-step retry deduplication")


class JoinGroupResponse(BaseModel):
    """Response model for join_group() function"""
    status: str = Field("success", description="Operation status")
    agent_id: int = Field(..., description="The ID of the agent")
    group_id: int = Field(..., description="The ID of the group")
    reason: str | None = Field(None, description="Failure reason, if any")
    already_member: bool = Field(False, description="Whether the agent was already a member")
    deduplicated: bool = Field(False, description="Whether this response came from same-step retry deduplication")


class LeaveGroupResponse(BaseModel):
    """Response model for leave_group() function"""
    status: str = Field("success", description="Operation status")
    agent_id: int = Field(..., description="The ID of the agent")
    group_id: int = Field(..., description="The ID of the group")
    reason: str | None = Field(None, description="Failure reason, if any")
    removed: bool = Field(False, description="Whether the agent was removed")
    deduplicated: bool = Field(False, description="Whether this response came from same-step retry deduplication")


class SendGroupMessageResponse(BaseModel):
    """Response model for send_group_message() function"""
    status: str = Field("success", description="Operation status")
    sender_id: int = Field(..., description="The ID of the sender agent")
    group_id: int = Field(..., description="The ID of the group")
    content: str = Field("", description="The content of the message")
    recipient_count: int = Field(0, description="The number of recipients")
    message_id: int | None = Field(None, description="The durable message identifier")
    step: int | None = Field(None, description="Simulation step in which the message was sent")
    reason: str | None = Field(None, description="Failure reason, if any")
    deduplicated: bool = Field(False, description="Whether this response came from same-step retry deduplication")


class SimpleSocialSpaceAuditable(EnvBase):
    # 声明式状态持久化
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("total_messages_sent", "INTEGER"),
        ColumnDef("active_groups", "INTEGER"),
        ColumnDef("total_agents", "INTEGER"),
    ]

    def __init__(
        self,
        agent_id_name_pairs: List[Tuple[int, str]] | List[List[int | str]] | None = None,
        enabled_tools: List[str] | None = None,
    ):
        """
        Initialize the Social Space environment.

        :param agent_id_name_pairs: List of (agent_id, name) tuples or list of [agent_id, name] lists. Can be tuples or lists of length 2. Defaults to empty (the scenario injects the real pairs at runtime; the default keeps the class instantiable with no args for the AS module scanner).
        """
        super().__init__()

        # Convert list format to tuple format if needed
        pairs: List[Tuple[int, str]] = []
        for pair in (agent_id_name_pairs or []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                pairs.append((int(pair[0]), str(pair[1])))
            else:
                raise ValueError(
                    f"Invalid agent_id_name_pair format: {pair}. Expected tuple/list of (int, str)"
                )

        # Individual mailboxes for agents
        self._mailboxes: Dict[int, List[Message]] = defaultdict(list)

        # Groups
        self._groups: Dict[int, Group] = {}
        self._next_group_id: int = 1
        self._next_message_id: int = 1

        # Names for agents and groups
        self._agent_names: Dict[int, str] = {agent_id: name for agent_id, name in pairs}

        # Lock for thread safety
        self._lock = asyncio.Lock()
        self._step_counter: int = 0
        self._total_messages_sent: int = 0
        self._dedup: Dict[str, dict] = {}
        # [research patch] durable append-only log of every message ever sent.
        self._message_log: List[dict] = []

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
                raise ValueError(f"unknown SimpleSocialSpace tools: {sorted(unknown_tools)}")
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

    async def to_workspace(self, workspace_path=None) -> None:
        """写入 ``state/ENV_STATE.json``（原子写）。pydantic 用 model_dump，``_lock`` 不存盘。"""
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("Env module workspace is not bound")
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(
                {
                    "mailboxes": {
                        str(aid): [m.model_dump(mode="json") for m in msgs]
                        for aid, msgs in self._mailboxes.items()
                    },
                    "groups": {
                        str(gid): g.model_dump(mode="json")
                        for gid, g in self._groups.items()
                    },
                    "next_group_id": self._next_group_id,
                    "next_message_id": self._next_message_id,
                    "agent_names": dump_int_map(self._agent_names),
                    "step_counter": self._step_counter,
                    "total_messages_sent": self._total_messages_sent,
                    "dedup": self._dedup,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
        # [research patch] write durable append-only message log (full rewrite, idempotent).
        log_path = self._workspace_root / _LOG_REL
        log_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            log_path,
            "\n".join(json.dumps(m, ensure_ascii=False) for m in self._message_log) + ("\n" if self._message_log else ""),
        )

    async def restore(self, workspace_path) -> bool:
        """从 ``state/ENV_STATE.json`` 恢复。

        ``_mailboxes`` 恢复为 ``defaultdict(list)``（工具方法依赖自动建键）；
        ``_lock`` 由 ``__init__`` 重建，不从盘读取。
        """
        self._bind_workspace(workspace_path)
        state_path = self._workspace_root / _STATE_REL
        if not state_path.is_file():
            return False
        state = json.loads(state_path.read_text(encoding="utf-8"))
        mailboxes = load_int_map(state.get("mailboxes"))
        self._mailboxes = defaultdict(
            list,
            {aid: [Message.model_validate(m) for m in msgs] for aid, msgs in mailboxes.items()},
        )
        groups = load_int_map(state.get("groups"))
        self._groups = {gid: Group.model_validate(g) for gid, g in groups.items()}
        self._next_group_id = int(state.get("next_group_id", 1))
        self._next_message_id = int(state.get("next_message_id", 1))
        self._agent_names = {
            aid: str(name) for aid, name in load_int_map(state.get("agent_names")).items()
        }
        self._step_counter = int(state.get("step_counter", 0))
        self._total_messages_sent = int(state.get("total_messages_sent", 0))
        self._dedup = state.get("dedup", {})
        # [research patch] restore durable message log if present.
        log_path = self._workspace_root / _LOG_REL
        self._message_log = []
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        self._message_log.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return True

    @classmethod
    def init_description(cls) -> str:
        """
        Return AI-readable initialization guidance for this environment module.
        Includes parameter descriptions and JSON schemas for data models.
        """

        description = f"""{cls.__name__}: Social communication environment module.

**Description:** Provides social communication functionalities including individual mailboxes and group messaging.

**Initialization Parameters (excluding llm):**
- agent_id_name_pairs (List[Tuple[int, str]] | List[List[int | str]]): List of (agent_id, name) pairs. Can be tuples or lists of length 2. Each element should be [agent_id (int), name (str)].
- enabled_tools (List[str] | None): Optional exact active surface. PIC-001 uses
  ``send_message`` and public ``read_messages``; ``receive_messages`` remains
  an internal compatibility implementation.

**Example initialization config:**
```json
{{
  "agent_id_name_pairs": [
    [1, "Alice"],
    [2, "Bob"],
    [3, "Charlie"]
  ]
}}
```
"""
        return description

    @classmethod
    def description(cls) -> str:
        """Return a short module description."""
        return "Social communication environment for direct messages and group interactions."

    def _known_agent(self, agent_id: int) -> bool:
        return int(agent_id) in self._agent_names

    # Mailbox functions
    @tool(readonly=False)
    async def send_message(
        self,
        sender_id: int,
        receiver_id: int,
        content: str,
    ) -> SendMessageResponse:
        """
        Send a message to an agent's mailbox.

        :param sender_id: The ID of the sender agent
        :param receiver_id: The ID of the receiver agent
        :param content: The content of the message

        :returns: Context containing message details
        """
        async with self._lock:
            content = str(content).strip()
            if not self._known_agent(sender_id):
                return SendMessageResponse(
                    status="fail", sender_id=sender_id, receiver_id=receiver_id,
                    content=content, reason=f"unknown sender_id {sender_id}",
                )
            if not self._known_agent(receiver_id):
                return SendMessageResponse(
                    status="fail", sender_id=sender_id, receiver_id=receiver_id,
                    content=content, reason=f"unknown receiver_id {receiver_id}",
                )
            if not content:
                return SendMessageResponse(
                    status="fail", sender_id=sender_id, receiver_id=receiver_id,
                    content=content, reason="content must not be empty",
                )
            key = json.dumps(
                [self._step_counter, "send_message", sender_id, receiver_id, content],
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            if key in self._dedup:
                return SendMessageResponse(**{**self._dedup[key], "deduplicated": True})
            # Create message
            timestamp = self.t
            message = Message(
                sender_id=sender_id,
                content=content,
                timestamp=timestamp,
                message_id=self._next_message_id,
                receiver_id=receiver_id,
            )
            self._next_message_id += 1

            # Add to receiver's mailbox
            self._mailboxes[receiver_id].append(message)
            self._total_messages_sent += 1
            # [research patch] durable log (not consumed on read) for audit.
            self._message_log.append({
                "message_id": message.message_id,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": content,
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                "group_id": None,
                "step": self._step_counter,
            })

            response = SendMessageResponse(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=content,
                message_id=message.message_id,
                step=self._step_counter,
            )
            self._dedup[key] = response.model_dump()
            return response

    def _read_messages_locked(self, agent_id: int, limit: int | None = None) -> list[dict]:
        """Read and consume mailbox messages without touching the audit log."""
        mailbox = self._mailboxes[agent_id]
        if limit is None:
            selected = list(mailbox)
            self._mailboxes[agent_id] = []
        else:
            limit = max(1, int(limit))
            selected = list(mailbox[:limit])
            self._mailboxes[agent_id] = mailbox[len(selected):]

        messages = []
        for message in selected:
            sender_name = self._agent_names.get(
                message.sender_id, f"Agent {message.sender_id}"
            )
            message_data = {
                "type": "personal",
                "message_id": message.message_id,
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id or agent_id,
                "sender_name": sender_name,
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "step": self._step_counter,
            }
            if message.group_id is not None:
                message_data["type"] = "group"
                message_data["group_id"] = message.group_id
                group_name = (
                    self._groups[message.group_id].name
                    if message.group_id in self._groups
                    else f"Group {message.group_id}"
                )
                message_data["group_name"] = group_name
            messages.append(message_data)
        return messages

    @tool(readonly=True, kind="observe")
    async def receive_messages(self, agent_id: int) -> ReceiveMessagesResponse:
        """
        Receive all messages from an agent's mailbox including personal messages and group messages.
        This is like an instant messaging app where all messages are received in one place.

        :param agent_id: The ID of the agent

        :returns: Context containing all messages
        """
        async with self._lock:
            if not self._known_agent(agent_id):
                return ReceiveMessagesResponse(
                    status="fail", agent_id=agent_id, messages=[], reason=f"unknown agent_id {agent_id}"
                )
            messages = self._read_messages_locked(agent_id)
            return ReceiveMessagesResponse(
                agent_id=agent_id,
                messages=messages,
            )

    @tool(readonly=True)
    async def read_messages(self, agent_id: int, request: dict | None = None) -> dict:
        """Read and consume the requesting agent's private mailbox.

        This is the public EW name for the auditable mailbox adapter. The
        internal ``receive_messages`` method remains registered for backwards
        compatibility but is intentionally omitted from a PIC-001 allowlist.

        :param agent_id: Agent whose own mailbox is read.
        :param request: Optional ``limit``; the append-only audit log is never consumed.
        """
        async with self._lock:
            if not self._known_agent(agent_id):
                return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
            request = request or {}
            messages = self._read_messages_locked(agent_id, request.get("limit"))
            return {
                "status": "success",
                "agent_id": int(agent_id),
                "messages": messages,
                "consumed_count": len(messages),
            }

    # Group functions
    @tool(readonly=False)
    async def create_group(
        self, creator_id: int, name: str, init_members: List[int]
    ) -> CreateGroupResponse:
        """
        Create a new group.

        :param creator_id: The ID of the agent creating the group
        :param name: The name of the group
        :param init_members: The initial members of the group

        :returns: Context containing group details
        """
        async with self._lock:
            creator_id = int(creator_id)
            if not self._known_agent(creator_id):
                return CreateGroupResponse(
                    status="fail", creator_id=creator_id, reason=f"unknown creator_id {creator_id}"
                )
            if not isinstance(name, str) or not name.strip():
                return CreateGroupResponse(
                    status="fail", creator_id=creator_id, reason="name must not be empty"
                )
            if not isinstance(init_members, list):
                return CreateGroupResponse(
                    status="fail", creator_id=creator_id, reason="init_members must be a list"
                )
            try:
                members = list(dict.fromkeys(int(member_id) for member_id in init_members))
            except (TypeError, ValueError):
                return CreateGroupResponse(
                    status="fail", creator_id=creator_id, reason="init_members must contain integer agent IDs"
                )
            unknown_members = [member_id for member_id in members if not self._known_agent(member_id)]
            if unknown_members:
                return CreateGroupResponse(
                    status="fail", creator_id=creator_id,
                    reason=f"unknown member IDs: {unknown_members}",
                )
            name = name.strip()
            key = json.dumps(
                [self._step_counter, "create_group", creator_id, name, members],
                ensure_ascii=False, sort_keys=True,
            )
            if key in self._dedup:
                return CreateGroupResponse(**{**self._dedup[key], "deduplicated": True})
            group_id = self._next_group_id
            self._next_group_id += 1

            group = Group(
                group_id=group_id,
                name=name,
                members=list(dict.fromkeys([creator_id, *members])),
            )

            self._groups[group_id] = group

            response = CreateGroupResponse(
                creator_id=creator_id,
                group_id=group_id,
                name=name,
            )
            self._dedup[key] = response.model_dump()
            return response

    @tool(readonly=False)
    async def join_group(self, agent_id: int, group_id: int) -> JoinGroupResponse:
        """
        Join an agent to a group.

        :param agent_id: The ID of the agent
        :param group_id: The ID of the group

        :returns: Context containing group and agent details
        """
        async with self._lock:
            agent_id = int(agent_id)
            group_id = int(group_id)
            key = json.dumps([self._step_counter, "join_group", agent_id, group_id], sort_keys=True)
            if key in self._dedup:
                return JoinGroupResponse(**{**self._dedup[key], "deduplicated": True})
            if not self._known_agent(agent_id):
                return JoinGroupResponse(status="fail", agent_id=agent_id, group_id=group_id, reason=f"unknown agent_id {agent_id}")
            # Check if group exists
            if group_id not in self._groups:
                return JoinGroupResponse(status="fail", agent_id=agent_id, group_id=group_id, reason=f"group {group_id} not found")

            # Check if agent is already in the group
            group = self._groups[group_id]
            if agent_id in group.members:
                response = JoinGroupResponse(agent_id=agent_id, group_id=group_id, already_member=True)
                self._dedup[key] = response.model_dump()
                return response

            # Add agent to group
            group.members.append(agent_id)

            response = JoinGroupResponse(agent_id=agent_id, group_id=group_id)
            self._dedup[key] = response.model_dump()
            return response

    @tool(readonly=False)
    async def leave_group(self, agent_id: int, group_id: int) -> LeaveGroupResponse:
        """
        Remove an agent from a group.

        :param agent_id: The ID of the agent
        :param group_id: The ID of the group

        :returns: Context containing group and agent details
        """
        async with self._lock:
            agent_id = int(agent_id)
            group_id = int(group_id)
            key = json.dumps([self._step_counter, "leave_group", agent_id, group_id], sort_keys=True)
            if key in self._dedup:
                return LeaveGroupResponse(**{**self._dedup[key], "deduplicated": True})
            if not self._known_agent(agent_id):
                return LeaveGroupResponse(status="fail", agent_id=agent_id, group_id=group_id, reason=f"unknown agent_id {agent_id}")
            # Check if group exists
            if group_id not in self._groups:
                return LeaveGroupResponse(status="fail", agent_id=agent_id, group_id=group_id, reason=f"group {group_id} not found")

            # Check if agent is in the group
            group = self._groups[group_id]
            if agent_id not in group.members:
                return LeaveGroupResponse(status="fail", agent_id=agent_id, group_id=group_id, reason=f"agent {agent_id} is not in group {group_id}")

            # Remove agent from group
            group.members.remove(agent_id)

            # If group is empty, remove it
            if len(group.members) == 0:
                del self._groups[group_id]

            response = LeaveGroupResponse(agent_id=agent_id, group_id=group_id, removed=True)
            self._dedup[key] = response.model_dump()
            return response

    @tool(readonly=False)
    async def send_group_message(
        self, sender_id: int, group_id: int, content: str
    ) -> SendGroupMessageResponse:
        """
        Send a message to all members of a group. The message is forwarded to each member's mailbox.

        :param sender_id: The ID of the sender agent
        :param group_id: The ID of the group
        :param content: The content of the message

        :returns: Context containing message details
        """
        async with self._lock:
            sender_id = int(sender_id)
            group_id = int(group_id)
            content = str(content).strip()
            key = json.dumps(
                [self._step_counter, "send_group_message", sender_id, group_id, content],
                ensure_ascii=False, sort_keys=True,
            )
            if key in self._dedup:
                return SendGroupMessageResponse(**{**self._dedup[key], "deduplicated": True})
            if not self._known_agent(sender_id):
                return SendGroupMessageResponse(status="fail", sender_id=sender_id, group_id=group_id, content=content, reason=f"unknown sender_id {sender_id}")
            if not content:
                return SendGroupMessageResponse(status="fail", sender_id=sender_id, group_id=group_id, content=content, reason="content must not be empty")
            # Check if group exists
            if group_id not in self._groups:
                return SendGroupMessageResponse(status="fail", sender_id=sender_id, group_id=group_id, content=content, reason=f"group {group_id} not found")

            # Check if sender is in the group
            group = self._groups[group_id]
            if sender_id not in group.members:
                return SendGroupMessageResponse(status="fail", sender_id=sender_id, group_id=group_id, content=content, reason=f"sender {sender_id} is not in group {group_id}")

            # Create message
            timestamp = self.t
            message = Message(
                sender_id=sender_id,
                content=content,
                timestamp=timestamp,
                message_id=self._next_message_id,
                group_id=group_id,
            )
            self._next_message_id += 1

            # Forward message to each member's mailbox (including sender)
            recipient_count = 0
            for member_id in group.members:
                self._mailboxes[member_id].append(message)
                recipient_count += 1
            self._total_messages_sent += 1
            self._message_log.append({
                "message_id": message.message_id,
                "sender_id": sender_id,
                "receiver_id": None,
                "content": content,
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                "group_id": group_id,
                "recipient_count": recipient_count,
                "step": self._step_counter,
            })

            response = SendGroupMessageResponse(
                sender_id=sender_id,
                group_id=group_id,
                content=content,
                recipient_count=recipient_count,
                message_id=message.message_id,
                step=self._step_counter,
            )
            self._dedup[key] = response.model_dump()
            return response

    async def step(self, tick: int, t: datetime):
        """
        Run forward one step.

        :param tick: The number of ticks of this simulation step.
        :param t: The current datetime of the simulation after this step with the ticks.
        """
        async with self._lock:
            self.t = t
            self._step_counter += 1
            self._dedup.clear()

            # Clean up empty groups
            groups_to_remove = []
            for group_id, group in self._groups.items():
                # If group is empty (no members), mark for removal
                if len(group.members) == 0:
                    groups_to_remove.append(group_id)

            # Remove empty groups
            for group_id in groups_to_remove:
                del self._groups[group_id]

        # 持久化环境全局状态
        await self._write_env_state(
            step=self._step_counter, t=t,
            total_messages_sent=self._total_messages_sent,
            active_groups=len(self._groups),
            total_agents=len(self._agent_names),
        )
