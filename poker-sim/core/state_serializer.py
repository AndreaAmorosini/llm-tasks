from typing import Any

from core.action_mapper import get_legal_actions


STREET_NAMES = {
    0: "preflop",
    1: "flop",
    2: "turn",
    3: "river",
}


def _card_to_compact_string(card) -> str:
    try:
        rank = str(card.rank)
        suit = getattr(card.suit, "value", str(card.suit))
        return f"{rank}{suit}"
    except Exception:
        return str(card)


def _cards_to_strings(cards) -> list[str]:
    return [_card_to_compact_string(card) for card in cards]


def _board_to_strings(state) -> list[str]:
    cards: list[str] = []

    try:
        for board_index in state.board_indices:
            cards.extend(_cards_to_strings(state.get_board(board_index)))
        return cards
    except Exception:
        return _cards_to_strings(getattr(state, "board_cards", []))


def _hero_cards(state, hero_index: int) -> list[str]:
    try:
        return _cards_to_strings(state.hole_cards[hero_index])
    except Exception:
        return []


def serialize_state_for_player(state, player_index: int) -> dict[str, Any]:
    street_index = getattr(state, "street_index", None)
    board = _board_to_strings(state)
    legal_actions = get_legal_actions(state)

    players = []
    active_players = 0

    for i in range(state.player_count):
        is_active = bool(state.statuses[i])
        if is_active:
            active_players += 1

        players.append(
            {
                "seat": i,
                "stack": int(state.stacks[i]),
                "bet": int(state.bets[i]),
                "active": is_active,
            }
        )

    hero_stack = int(state.stacks[player_index])
    hero_bet = int(state.bets[player_index])
    max_bet = max(int(x) for x in state.bets) if state.bets else 0
    to_call = max(0, max_bet - hero_bet)

    compact_state = {
        "street": STREET_NAMES.get(street_index, f"street_{street_index}"),
        "hero": {
            "seat": player_index,
            "cards": _hero_cards(state, player_index),
            "stack": hero_stack,
            "bet": hero_bet,
        },
        "board": board,
        "pot": int(getattr(state, "total_pot_amount", 0)),
        "to_call": to_call,
        "active_players": active_players,
        "players": players,
    }

    return {
        "state": compact_state,
        "legal_actions": legal_actions,
    }