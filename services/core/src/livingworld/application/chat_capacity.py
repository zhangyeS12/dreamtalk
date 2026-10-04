"""Pack authorized dialogue inputs; numeric admission still uses trusted bounds."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from livingworld.application.llm import MessageRole, TextContent
from livingworld.application.llm_budget import BoundGuarantee, prepare_usage_bound


@dataclass(frozen=True, slots=True)
class ContextLayout:
    # Indexes refer to builder-generated input, never provider output or arbitrary text.
    direct_turns: tuple[tuple[int, ...], ...] = ()
    group_turns: tuple[tuple[int, ...], ...] = ()
    current_turn: int = -1
    message_ids: tuple[str, ...] = ()
    retrieval: str = "keyword"


class ContextCapacityError(ValueError):
    pass


@dataclass
class ContextPacker:
    request: object = field(repr=False)
    layout: ContextLayout = ContextLayout()

    def __post_init__(self):
        self.messages = list(self.request.messages)
        # Annotation transport can insert system messages ahead of the persona.
        self.persona_index = next(
            index
            for index, message in enumerate(self.messages)
            if message.role is not MessageRole.SYSTEM
        )
        self.offset = self.persona_index - 1
        self.data = json.loads(self.messages[self.persona_index].content[0].text)
        self.original = json.loads(json.dumps(self.data))
        self.units = []
        for key, priority in {
            "group_messages_seen": 10,
            "other_group_messages_seen": 10,
            "character_observed_world_events": 20,
            "earlier_dialogue_quotes": 30,
            "long_term_original_quotes": 30,
            "common_world_background": 40,
            "character_memories": 45,
            "long_term_dialogue_memories": 65,
        }.items():
            values = self.data.get(key, [])
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                score = priority
                if (
                    key == "character_observed_world_events"
                    and value.get("recall_basis") == "topic_match"
                ):
                    score = 55
                if key == "long_term_dialogue_memories":
                    score = 90 if value.get("kind") in {"identity", "preference", "promise"} else 65
                    # The reader orders pinned/core/related; first entries get priority.
                    score += max(0, 8 - index)
                self.units.append((score, key, index))
        if self.data.get("known_faction_contacts"):
            self.units.append((70, "known_faction_contacts", None))
        if "confirmed_conversation_summary" in self.data:
            self.units.append((80, "confirmed_conversation_summary", None))
        character = self.data.get("character", {})
        if "opening_style_example" in character:
            self.units.append((15, "opening_style_example", None))
        for key, turns in (
            ("direct_history", self.layout.direct_turns),
            ("group_history", self.layout.group_turns),
        ):
            current = self.layout.current_turn if self.layout.current_turn >= 0 else len(turns) - 1
            for index in range(len(turns)):
                if index != current:
                    self.units.append((50 + min(index, 30), key, index))
        self.units.sort(key=lambda unit: unit[0])
        self.available = list(self.units)
        self.dropped = []

    def render(self):
        data = json.loads(json.dumps(self.data))
        omitted = {}
        for _priority, key, index in self.dropped:
            omitted.setdefault(key, set()).add(index)
        for key, indexes in omitted.items():
            if key == "opening_style_example":
                data["character"].pop(key, None)
            elif key in {"confirmed_conversation_summary", "known_faction_contacts"}:
                data.pop(key, None)
            elif key == "group_history":
                removed = {
                    position for index in indexes for position in self.layout.group_turns[index]
                }
                data["transcript"] = [
                    item for index, item in enumerate(data["transcript"]) if index not in removed
                ]
            elif key != "direct_history":
                data[key] = [value for index, value in enumerate(data[key]) if index not in indexes]
        removed = {
            message + self.offset
            for _score, key, index in self.dropped
            if key == "direct_history"
            for message in self.layout.direct_turns[index]
        }
        result = []
        for index, message in enumerate(self.messages):
            if index in removed:
                continue
            if index == self.persona_index:
                message = replace(
                    message,
                    content=(
                        TextContent(json.dumps(data, ensure_ascii=False, separators=(",", ":"))),
                    ),
                )
            result.append(message)
        self.final_data = data
        return replace(self.request, messages=tuple(result))

    def drop_batch(self):
        # Bound preflight passes, including providers with a remote count endpoint.
        count = max(1, (len(self.available) + 1) // 2)
        self.dropped.extend(self.available[:count])
        del self.available[:count]

    def report(self, request, bound, remaining):
        categories = []
        labels = {
            "known_faction_contacts": "已确认阵营与相识",
            "common_world_background": "公共世界背景",
            "long_term_dialogue_memories": "长期对话记忆",
            "long_term_original_quotes": "历史原句",
            "group_messages_seen": "已参与的群聊",
            "other_group_messages_seen": "已参与的群聊",
            "confirmed_conversation_summary": "已确认摘要",
        }
        references = []
        for key, label in labels.items():
            before = self.original.get(key)
            if before is None:
                continue
            after = self.final_data.get(key)
            total = len(before) if isinstance(before, list) else 1
            kept = len(after) if isinstance(after, list) else int(after is not None)
            categories.append({"label": label, "included": kept, "omitted": total - kept})
            if key in {"long_term_dialogue_memories", "long_term_original_quotes"}:
                for value in after or []:
                    # Shared dialogue only; never expose private episodic state or activity.
                    references.append(
                        {
                            "kind": "memory" if key.endswith("memories") else "quote",
                            "id": value.get("entry_id") or value.get("message_id"),
                            "text": value.get("content")
                            or value.get("text")
                            or value.get("quote", ""),
                            "source": value.get("quote", "")
                            if value.get("quote")
                            != (value.get("content") or value.get("text") or value.get("quote"))
                            else "",
                            "time": value.get("created_at", ""),
                            "source_kind": value.get("source_kind", ""),
                            "source_sender_id": value.get("source_sender_id", ""),
                        }
                    )
        if self.layout.direct_turns:
            total = sum(map(len, self.layout.direct_turns))
            omitted = sum(
                len(self.layout.direct_turns[index])
                for _, key, index in self.dropped
                if key == "direct_history"
            )
        else:
            total = sum(map(len, self.layout.group_turns))
            omitted = total - len(self.final_data.get("transcript", []))
        categories.append({"label": "近期对话", "included": total - omitted, "omitted": omitted})
        report = {
            "version": 1,
            "input_upper_bound": bound,
            "output_upper_bound": request.max_output_tokens,
            "remaining_before_call": remaining,
            "retrieval": self.layout.retrieval,
            "categories": categories,
            "references": references[:20],
            "context_reduced": bool(self.dropped),
        }
        report["references_omitted"] = 0
        while (
            len(json.dumps(report, ensure_ascii=False).encode("utf-8")) > 24576
            and report["references"]
        ):
            report["references"].pop()
            report["references_omitted"] += 1
        return report


async def fit_chat_context(request, layout, gateway, bounder, selection, remaining):
    """Only remove optional whole units; never cut the current question/turn or persona."""
    plan = gateway.plan(request, selection=selection)
    packer = ContextPacker(request, layout or ContextLayout())
    reserve = min(request.max_output_tokens, 2048, max(1, remaining // 4))
    for _ in range(12):
        fitted = packer.render()
        bounds = [
            await prepare_usage_bound(bounder, replace(fitted, model=model))
            for model in plan.candidates
        ]
        if not bounds or any(
            b is None or b.guarantee is not BoundGuarantee.HARD_UPPER_BOUND for b in bounds
        ):
            raise ContextCapacityError("turn_input_bound_unavailable")
        input_bound = max(b.input_tokens for b in bounds)
        room = remaining - input_bound
        feedback = getattr(bounder, "packing_feedback", lambda request: None)
        capacities = [feedback(replace(fitted, model=model)) for model in plan.candidates]
        measurable = all(value is not None for value in capacities)
        over_capacity = any(value is not None and value[0] > value[1] for value in capacities)
        # A model-wide financial bound cannot shrink with text. Do not throw away
        # useful history when this provider offers no request-specific measurement.
        if not over_capacity and (room >= reserve or not measurable or not packer.available):
            if room < 1:
                raise ContextCapacityError("turn_token_limit_exceeded")
            fitted = replace(fitted, max_output_tokens=min(fitted.max_output_tokens, room))
            # Output changes can affect provider framing: always verify the final request.
            final = [
                await prepare_usage_bound(bounder, replace(fitted, model=model))
                for model in plan.candidates
            ]
            if any(
                b is None
                or b.guarantee is not BoundGuarantee.HARD_UPPER_BOUND
                or b.input_tokens + b.output_tokens > remaining
                for b in final
            ):
                raise ContextCapacityError("turn_token_limit_exceeded")
            return fitted, packer.report(fitted, max(b.input_tokens for b in final), remaining)
        if not packer.available:
            raise ContextCapacityError("turn_token_limit_exceeded")
        packer.drop_batch()
    raise ContextCapacityError("turn_token_limit_exceeded")
