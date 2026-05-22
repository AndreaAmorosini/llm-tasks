import random
from typing import Any

class RandomAgent:
    def __init__(self, name: str = "RandomAgent"):
        self.name = name
        
    def decide_action(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        return random.choice(legal_actions)