from typing import Any, Protocol

Action = dict[str, Any]
PublicState = dict[str, Any]

class Agent(Protocol):
    name: str
    
    def decide_action(self, public_state: PublicState, legal_actions: list[Action]) -> Action:
        ...