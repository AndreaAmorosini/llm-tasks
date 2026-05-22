import json
from typing import Any


class LLMAgent:
    def __init__(self, client, model: str, name: str = "LLMAgent"):
        self.client = client
        self.model = model
        self.name = name

    def decide_action(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = self._build_prompt(public_state, legal_actions)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a No-Limit Texas Hold'em poker player. "
                        "Choose exactly one legal action. "
                        "Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        content = response.choices[0].message.content

        try:
            action = json.loads(content)
        except Exception:
            return self._fallback(legal_actions)

        return self._validate_or_fallback(action, legal_actions)

    def _build_prompt(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]],) -> str:
        return json.dumps(
            {
                "instruction": (
                    "Choose one action from legal_actions. "
                    "For bet/raise/all_in use amount_to, not incremental amount."
                ),
                "state": public_state,
                "legal_actions": legal_actions,
                "output_schema": {
                    "type": "fold|check|call|bet|raise|all_in",
                    "amount_to": "integer optional",
                    "reason": "short explanation optional",
                },
            },
            indent=2,
        )

    def _validate_or_fallback(self, action: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        requested_type = action.get("type")

        for legal in legal_actions:
            if legal["type"] != requested_type:
                continue

            if requested_type in {"fold", "check", "call"}:
                return legal

            if requested_type in {"bet", "raise", "all_in"}:
                requested = int(
                    action.get(
                        "amount_to",
                        action.get("amount", legal.get("amount_to", legal.get("min", 0))),
                    )
                )
                return {
                    **legal,
                    "amount_to": max(int(legal["min"]), min(requested, int(legal["max"]))),
                }

        return self._fallback(legal_actions)

    def _fallback(self, legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        for action in legal_actions:
            if action["type"] == "check":
                return action

        for action in legal_actions:
            if action["type"] == "fold":
                return action

        return legal_actions[0]