from typing import Any

class TightPassiveAgent:
    def __init__(self, name: str = "TightPassiveAgent", max_call: int = 50):
        self.name = name
        self.max_call = max_call
        
    def decide_action(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        for action in legal_actions:
                    if action["type"] == "check":
                        return action

        for action in legal_actions:
            if action["type"] == "call" and int(action.get("amount", 0)) <= self.max_call:
                return action

        for action in legal_actions:
            if action["type"] == "fold":
                return action

        return legal_actions[0] if legal_actions else {"type": "fold"}