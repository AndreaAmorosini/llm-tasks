from __future__ import annotations
from typing import Any

def to_pokerbots_valid_actions(state) -> dict[str, Any]:
    valid_actions: dict[str, Any] = {}
    
    if state.can_fold():
        valid_actions["fold"] = 0
        
    if state.can_check_or_call():
        valid_actions["check_or_call"] = int(
            getattr(state, "checking_or_calling_amount", 0) or 0
        )
        
    if state.can_complete_bet_or_raise_to():
        valid_actions["complete_bet_or_raise_to"] = (
            int(state.min_completion_betting_or_raising_to_amount),
            int(state.max_completion_betting_or_raising_to_amount)
        )
        
    return valid_actions

def from_pokerbots_action(state, action_name: str, amount: float | int) -> dict[str, Any]:
    action_name = str(action_name)
    
    if action_name == "fold":
        return {"type": "fold"}
    
    if action_name == "check_or_call":
        call_amount = int(getattr(state, "checking_or_calling_amount", 0) or 0)
        if call_amount == 0:
            return {"type": "check", "amount": 0}
        return {"type": "call", "amount": call_amount}
    
    if action_name == "complete_bet_or_raise_to":
        current_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
        action_type = "bet" if current_call == 0 else "raise"
        return {"type": action_type, "amount": int(amount)}
    
    raise ValueError(f"Invalid action name from PokerBots: {action_name}")

def is_pokerbots_agent(agent: Any) -> bool:
    return callable(getattr(agent, "play", None))