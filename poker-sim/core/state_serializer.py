from typing import Any
from core.action_mapper import get_legal_actions

STREET_NAMES = {
    0: "preflop",
    1: "flop",
    2: "turn",
    3: "river"
}

def _cards_to_string(cards) -> list[str]:
    return [str(card) for card in cards]

def _board_to_strings(state) -> list[str]:
    cards: list[str] = []
    
    try:
        for board_index in state.board_indices:
            cards.extend(_cards_to_string(state.get_board(board_index)))
        return cards
    except Exception:
        return _cards_to_string(getattr(state, "board_cards", []))
    
def _hero_cards(state, hero_index: int) -> list[str]:
    try:
        return _cards_to_string(state.hole_cards[hero_index])
    except Exception:
        return []
    
def _visible_hole_cards(state, viewer_index: int, player_index: int) -> list[str]:
    if player_index == viewer_index:
        return _hero_cards(state, player_index)
    
    try:
        return _cards_to_string(state.get_censored_hole_cards(player_index))
    except Exception:
        return []
    
def serialize_state_for_player(state, player_index: int) -> dict[str, Any]:
    actor_index = getattr(state, "actor_index", None)
    street_index = getattr(state, "street_index", None)
    
    players = []
    
    for i in range(state.player_count):
        players.append(
            {
                "index": i,
                "name": f"Player_{i}",
                "stack": int(state.stacks[i]),
                "current_bet": int(state.bets[i]),
                "active": bool(state.statuses[i]),
                "hole_cards": _visible_hole_cards(state, player_index, i)
            }
        )
    
    return {
        "game": "No-Limit Texas Hold'em",
        "street": STREET_NAMES.get(street_index, f"street_{street_index}"),
        "street_index": street_index,
        "hero_index": player_index,
        "to_act": actor_index,
        "hero": players[player_index],
        "players": players,
        "board": _board_to_strings(state),
        "pot": int(getattr(state, "total_pot_amount", 0)),
        "stacks": [int(x) for x in state.stacks],
        "bets": [int(x) for x in state.bets],
        "payoffs": [int(x) for x in getattr(state, "payoffs", [])],
        "status": bool(state.status),
        "all_in_status": bool(getattr(state, "all_in_status", False)),
        "folded_status": bool(getattr(state, "folded_status", False)),
        "legal_actions": get_legal_actions(state)
    }