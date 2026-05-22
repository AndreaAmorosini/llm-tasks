from typing import Any

Action = dict[str, Any]

def get_legal_actions(state) -> list[Action]:
    actions: list[Action] = []
    
    if state.can_fold():
        actions.append({'type': 'fold'})
        
    if state.can_check_or_call():
        call_amount = int(getattr(state, "checking_or_calling_amount", 0) or 0)
        if call_amount == 0:
            actions.append({"type": "check", "amount": 0})
        else:
            actions.append({"type": "call", "amount": call_amount})
            
    if state.can_complete_bet_or_raise_to():
        min_to = int(state.min_completion_betting_or_raising_to_amount)
        max_to = int(state.max_completion_betting_or_raising_to_amount)
        
        current_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
        action_type = "bet" if current_call == 0 else "raise"
        
        actions.append(
            {
                "type": action_type,
                "min": min_to,
                "max": max_to,
                "amount_to": min_to
            }
        )
        
        actions.append(
            {
                "type": action_type,
                "min": min_to,
                "max": max_to,
                "amount_to": max_to
            }
        )
        
    return actions

def sanitize_action(action: Action, legal_actions: list[Action]) -> Action:
    if not legal_actions:
        raise ValueError("No legal actions available")
    
    action_type = action.get("type")
    
    for legal in legal_actions:
        if legal["type"] != action_type:
            continue
        
        if action_type in {"fold", "check", "call"}:
            return legal
        
        if action_type in {"bet", "raise", "all_in"}:
            requested = int(action.get("amount_to", action.get("amount", legal.get("amount_to", legal.get("min", 0)))))
            min_to = int(legal["min"])
            max_to = int(legal["max"])
            amount_to = max(min_to, min(requested, max_to))
            
            return {
                **legal,
                "amount_to": amount_to
            }
            
    return legal_actions[0]

def apply_action(state, action: Action) -> None:
    action_type = action["type"]
    
    if action_type == "fold":
        state.fold()
    elif action_type in {"check", "call"}:
        state.check_or_call()
    elif action_type in {"bet", "raise", "all_in"}:
        amount_to = int(action.get("amount_to", action.get("amount", 0)))
        state.complete_bet_or_raise_to(amount_to)
    else:
        raise ValueError(f"Unknown action type: {action_type}")
    
    return