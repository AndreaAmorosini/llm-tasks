from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STREET_NAMES = {
    0: "preflop",
    1: "flop",
    2: "turn",
    3: "river"
}

def cards_to_strings(cards) -> list[str]:
    return [str(card) for card in cards]

def get_street_name(state) -> str:
    street_index = getattr(state, "street_index", None)
    return STREET_NAMES.get(street_index, f"street_{street_index}")

def get_board_cards(state) -> list[str]:
    cards: list[str] = []
    
    try:
        for board_index in state.board_indices:
            cards.extend(cards_to_strings(state.get_board(board_index)))
        return cards
    except Exception:
        return cards_to_strings(getattr(state, "board_cards", []))
    
def get_hole_cards(state, player_index: int) -> list[str]:
    try:
        return cards_to_strings(state.hole_cards[player_index])
    except Exception:
        return []
    
@dataclass
class ActionLog:
    step:int
    street: str
    actor_index: int
    agent_name: str
    board: list[str]
    stacks_before: list[int]
    bets_before: list[int]
    pot_before: int
    legal_actions: list[dict[str, Any]]
    raw_action: dict[str, Any]
    applied_action: dict[str, Any]
    decision_meta: dict[str, Any] | None = None
    stacks_after: list[int] | None = None
    bets_after: list[int] | None = None
    pot_after: int | None = None
    
    
@dataclass
class HandLog:
    hand_number: int
    player_count: int
    starting_stacks: list[int]
    hole_cards: dict[int, list[str]] = field(default_factory=dict)
    actions: list[ActionLog] = field(default_factory=list)
    final_board: list[str] = field(default_factory=list)
    final_stacks: list[int] = field(default_factory=list)
    payoffs: list[int] = field(default_factory=list)
    pokerkit_operations: list[str] = field(default_factory=list)
    hand_seed: int | None = None
    
class HandLogger:
    def __init__(
        self,
        hand_number: int,
        state,
        reveal_hole_cards: bool = True,
        include_legal_actions: bool = True,
        include_pokerkit_operations: bool = False,
        player_labels: dict[int, str] | None = None,
        hand_seed: int | None = None
    ):
        self.reveal_hole_cards = reveal_hole_cards
        self.include_legal_actions = include_legal_actions
        self.include_pokerkit_operations = include_pokerkit_operations
        
        self.player_labels = player_labels or {
            i: f"P{i}"
            for i in range(state.player_count)
        }
        
        self.hand = HandLog(
            hand_number = hand_number,
            player_count = state.player_count,
            starting_stacks = [int(x) for x in state.starting_stacks],
            hand_seed = hand_seed
        )
        
        if reveal_hole_cards:
            self.capture_hole_cards(state)
            
    def capture_hole_cards(self, state) -> None:
        self.hand.hole_cards = {
            i: get_hole_cards(state, i)
            for i in range(state.player_count)
        }
        
    def before_action(
        self,
        *,
        step: int,
        state,
        actor_index: int,
        agent_name: str,
        legal_actions: list[dict[str, Any]],
        raw_action: dict[str, Any],
        applied_action: dict[str, Any],
        decision_meta: dict[str, Any] | None = None
    ) -> int:
        
        action = ActionLog(
            step=step,
            street=get_street_name(state),
            actor_index=actor_index,
            agent_name=agent_name,
            board=get_board_cards(state),
            stacks_before=[int(x) for x in state.stacks],
            bets_before=[int(x) for x in state.bets],
            pot_before=int(getattr(state, "total_pot_amount", 0)),
            legal_actions=legal_actions if self.include_legal_actions else [],
            raw_action=raw_action,
            applied_action=applied_action,
            decision_meta=decision_meta
        )
        
        self.hand.actions.append(action)
        
        return len(self.hand.actions) - 1
    
    def after_action(self, action_log_index: int, state) -> None:
        action = self.hand.actions[action_log_index]
        
        action.stacks_after = [int(x) for x in state.stacks]
        action.bets_after = [int(x) for x in state.bets]
        action.pot_after = int(getattr(state, "total_pot_amount", 0))
        
    def finish(self, state) -> HandLog:            
        self.hand.final_board = get_board_cards(state)
        self.hand.final_stacks = [int(x) for x in state.stacks]
        self.hand.payoffs = [int(x) for x in state.payoffs]
        
        if self.include_pokerkit_operations:
            self.hand.pokerkit_operations = [str(op) for op in state.operations]
            
        return self.hand

    def to_dict(self) -> dict[str, Any]:
        return {
            "hand_number": self.hand.hand_number,
            "hand_seed": self.hand.hand_seed,
            "player_count": self.hand.player_count,
            "starting_stacks": self.hand.starting_stacks,
            "hole_cards": self.hand.hole_cards,
            "actions": [
                {
                    "step": action.step,
                    "street": action.street,
                    "actor_index": action.actor_index,
                    "agent_name": action.agent_name,
                    "board": action.board,
                    "stacks_before": action.stacks_before,
                    "bets_before": action.bets_before,
                    "pot_before": action.pot_before,
                    "legal_actions": action.legal_actions,
                    "raw_action": action.raw_action,
                    "applied_action": action.applied_action,
                    "stacks_after": action.stacks_after,
                    "bets_after": action.bets_after,
                    "pot_after": action.pot_after,
                    "decision_meta": action.decision_meta,
                }
                for action in self.hand.actions
            ],
            "final_board": self.hand.final_board,
            "final_stacks": self.hand.final_stacks,
            "payoffs": self.hand.payoffs,
            "pokerkit_operations": self.hand.pokerkit_operations,
        }

    def format_text(self) -> str:
        lines: list[str] = []

        lines.append("=" * 80)
        lines.append(f"HAND #{self.hand.hand_number}")
        lines.append(f"Hand seed: {self.hand.hand_seed}" if self.hand.hand_seed is not None else "Hand seed: None")
        lines.append("=" * 80)
        lines.append(f"Starting stacks: {self.hand.starting_stacks}")
        lines.append("")

        if self.hand.hole_cards:
            lines.append("Hole cards:")
            for player_index, cards in self.hand.hole_cards.items():
                label = self.player_labels.get(player_index, f"P{player_index}")
                lines.append(f"  {label}: {' '.join(cards) if cards else '[]'}")
            lines.append("")

        current_street = None

        for action in self.hand.actions:
            if action.street != current_street:
                current_street = action.street
                board = " ".join(action.board) if action.board else "-"
                lines.append(f"--- {current_street.upper()} | Board: {board} ---")

            applied = action.applied_action
            action_type = applied["type"]

            if action_type in {"bet", "raise", "all_in"}:
                rendered_action = f"{action_type} to {applied.get('amount_to')}"
            elif action_type == "call":
                rendered_action = f"call {applied.get('amount', 0)}"
            else:
                rendered_action = action_type

            lines.append(
                f"[{action.step:03d}] "
                f"{self.player_labels.get(action.actor_index, f'P{action.actor_index}')} "
                f"({action.agent_name}) -> {rendered_action}"
            )
            lines.append(
                f"      before: pot={action.pot_before}, "
                f"stacks={action.stacks_before}, bets={action.bets_before}"
            )

            if action.pot_after is not None:
                lines.append(
                    f"      after : pot={action.pot_after}, "
                    f"stacks={action.stacks_after}, bets={action.bets_after}"
                )

        lines.append("")
        lines.append(f"Final board: {' '.join(self.hand.final_board) if self.hand.final_board else '-'}")
        lines.append(f"Final stacks: {self.hand.final_stacks}")
        lines.append(f"Payoffs: {self.hand.payoffs}")

        if self.hand.pokerkit_operations:
            lines.append("")
            lines.append("PokerKit operations:")
            for operation in self.hand.pokerkit_operations:
                lines.append(f"  {operation}")

        lines.append("=" * 80)

        return "\n".join(lines)
    
    def to_reasoning_dict(self) -> dict[str, Any]:
        return {
            "hand_number": self.hand.hand_number,
            "player_count": self.hand.player_count,
            "actions": [
                {
                    "step": action.step,
                    "street": action.street,
                    "actor_index": action.actor_index,
                    "player_label": self.player_labels.get(action.actor_index, f"P{action.actor_index}"),
                    "agent_name": action.agent_name,
                    "own_hole_cards": self.hand.hole_cards.get(action.actor_index, []),
                    "board": action.board,
                    "raw_action": action.raw_action,
                    "applied_action": action.applied_action,
                    "decision_meta": action.decision_meta,
                    "reasoning_summary": (
                        action.decision_meta.get("response_thinking")
                        if action.decision_meta and action.decision_meta.get("response_thinking")
                        else action.decision_meta.get("final_reason")
                        if action.decision_meta
                        else None
                    ),
                    "motivation": (
                        action.decision_meta.get("motivation")
                        if action.decision_meta and action.decision_meta.get("motivation")
                        else None
                    ),
                    "player_stack_before_action": (
                        action.stacks_before[action.actor_index]
                        if action.stacks_before and len(action.stacks_before) > action.actor_index
                        else None
                    ),
                    "player_current_bet_before_action": (
                        action.bets_before[action.actor_index]
                        if action.bets_before and len(action.bets_before) > action.actor_index
                        else None
                    ),
                    "pot_size_before_action": action.pot_before,
                }
                for action in self.hand.actions
                if action.decision_meta is not None
            ],
        }