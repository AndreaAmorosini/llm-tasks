from __future__ import annotations

from collections import defaultdict
from typing import Any


class LLMStatsTracker:
    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        *,
        hand_number: int,
        step: int,
        street: str,
        player_label: str,
        agent_name: str,
        decision_meta: dict[str, Any] | None,
    ) -> None:
        if not decision_meta:
            return

        if decision_meta.get("agent_type") != "ollama":
            return

        self.events.append(
            {
                "hand_number": hand_number,
                "step": step,
                "street": street,
                "player_label": player_label,
                "agent_name": agent_name,
                **decision_meta,
            }
        )

    def summarize(self, hands_played: int) -> dict[str, Any]:
        total_calls = len(self.events)

        if total_calls == 0:
            return {
                "enabled": False,
                "total_calls": 0,
                "hands_played": hands_played,
            }

        total_latency = sum(float(e.get("latency_seconds") or 0.0) for e in self.events)
        fallback_count = sum(1 for e in self.events if e.get("fallback_used"))
        illegal_count = sum(1 for e in self.events if e.get("illegal_action_returned"))

        speeds = [
            float(e.get("generation_tokens_per_second"))
            for e in self.events
            if e.get("generation_tokens_per_second") is not None
        ]

        per_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        per_model: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for event in self.events:
            per_agent[event.get("agent_name", "unknown")].append(event)
            per_model[event.get("model", "unknown")].append(event)

        return {
            "enabled": True,
            "hands_played": hands_played,
            "total_calls": total_calls,
            "total_time_seconds": total_latency,
            "average_time_per_hand_seconds": (total_latency / hands_played) if hands_played else None,
            "average_latency_seconds": total_latency / total_calls,
            "average_generation_tokens_per_second": (sum(speeds) / len(speeds)) if speeds else None,
            "fallback_count": fallback_count,
            "illegal_action_count": illegal_count,
            "per_agent": {
                agent_name: self._group_summary(events, hands_played)
                for agent_name, events in per_agent.items()
            },
            "per_model": {
                model_name: self._group_summary(events, hands_played)
                for model_name, events in per_model.items()
            },
            "events": self.events,
        }

    def _group_summary(self, events: list[dict[str, Any]], hands_played: int) -> dict[str, Any]:
        total_calls = len(events)
        total_latency = sum(float(e.get("latency_seconds") or 0.0) for e in events)
        fallback_count = sum(1 for e in events if e.get("fallback_used"))
        illegal_count = sum(1 for e in events if e.get("illegal_action_returned"))

        speeds = [
            float(e.get("generation_tokens_per_second"))
            for e in events
            if e.get("generation_tokens_per_second") is not None
        ]

        return {
            "total_calls": total_calls,
            "total_time_seconds": total_latency,
            "average_time_per_hand_seconds": (total_latency / hands_played) if hands_played else None,
            "average_latency_seconds": (total_latency / total_calls) if total_calls else None,
            "average_generation_tokens_per_second": (sum(speeds) / len(speeds)) if speeds else None,
            "fallback_count": fallback_count,
            "illegal_action_count": illegal_count,
        }