from dataclasses import dataclass
from typing import Any
import random

from pokerkit import Automation, Mode, NoLimitTexasHoldem

from agents.base import Agent
from core.action_mapper import apply_action, get_legal_actions, sanitize_action
from core.config import GameConfig
from core.hand_logger import HandLogger
from core.state_serializer import serialize_state_for_player
from core.llm_stats import LLMStatsTracker

from agents.pokerbots_bridge import (
    from_pokerbots_action,
    is_pokerbots_agent,
    to_pokerbots_valid_actions
)

@dataclass
class TournamentPlayer:
    global_id: int
    agent: Agent
    stack: int
    eliminated: bool = False
    eliminated_hand: int | None = None

class PokerGame:
    def __init__(self, config: GameConfig, agents: list[Agent], verbose: bool = False, reveal_hole_cards: bool = False, include_legal_actions_in_log: bool = False, include_pokerkit_operations: bool = False):
        if len(agents) != config.player_count:
            raise ValueError(f"Number of agents ({len(agents)}) must match player count in config ({config.player_count})")
        
        self.config = config
        self.seed = config.seed
        self.verbose = verbose
        self.reveal_hole_cards = reveal_hole_cards
        self.include_legal_actions_in_log = include_legal_actions_in_log
        self.include_pokerkit_operations = include_pokerkit_operations
        self.llm_stats = LLMStatsTracker()
        
        self.players: list[TournamentPlayer] = [
            TournamentPlayer(
                global_id=i,
                agent=agent,
                stack=config.starting_stack
            )
            for i, agent in enumerate(agents)
        ]
                
        self.state = None
        self.hand_number = 0
        
        self.current_hand_player_ids: list[int] = []
        self.current_hand_players: list[TournamentPlayer] = []
        
        self.match_log: dict[str, Any] = {
            "seed": self.seed,
            "starting_player_count": config.player_count,
            "starting_stack": config.starting_stack,
            "hands": [],
            "eliminations": [],
            "winner": None,
        }

    @property
    def active_players(self) -> list[TournamentPlayer]:
        return [
            player for player in self.players if not player.eliminated and player.stack > 0
        ]
        
    @property
    def is_finished(self) -> bool:
        return len(self.active_players) <= 1
    
    @property
    def winner(self) -> TournamentPlayer | None:
        active = self.active_players
        if len(active) == 1:
            return active[0]
        return None
    
    def _compute_hand_seed(self) -> int | None:
        if self.seed is None:
            return None
        return self.seed + self.hand_number

    def create_state(self):
        active_players = self.active_players
        
        if len(active_players) < 2:
            raise RuntimeError("Not enough active players to start a hand.")
        
        self.current_hand_players = active_players
        self.current_hand_player_ids = [p.global_id for p in active_players]
        
        stacks = tuple(player.stack for player in active_players)
        
        hand_seed = self._compute_hand_seed()
        if hand_seed is not None:
            random.seed(hand_seed)
        
        return NoLimitTexasHoldem.create_state(
            (
                Automation.ANTE_POSTING,
                Automation.BET_COLLECTION,
                Automation.BLIND_OR_STRADDLE_POSTING,
                Automation.CARD_BURNING,
                Automation.HOLE_DEALING,
                Automation.BOARD_DEALING,
                Automation.RUNOUT_COUNT_SELECTION,
                Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
                Automation.HAND_KILLING,
                Automation.CHIPS_PUSHING,
                Automation.CHIPS_PULLING,
            ),
            True,  # is_automated
            self.config.ante,
            self.config.blinds,
            self.config.min_bet,
            stacks,
            len(active_players),
            mode = Mode.CASH_GAME
        )
        
    def play_match(self, max_hands: int | None = None)-> dict[str, Any]:
        
        if max_hands is None:
            max_hands = self.config.max_hands
                
        while not self.is_finished:
            if max_hands is not None and self.hand_number >= max_hands:
                break
            
            self.play_hand()
            
        winner = self.winner
            
        if winner is not None:
            self.match_log["winner"] = {
                "global_id": winner.global_id,
                "agent_name": winner.agent.name,
                "stack": winner.stack,
            }
            
        self.match_log["final_players"] = self.players_summary()
        self.match_log["finished"] = self.is_finished
        self.match_log["hands_played"] = self.hand_number
        self.match_log["match_text_log"] = self.format_full_match_log()
        
        if self.verbose:
            print(self.format_match_summary())
            
        self.match_log["reasoning_log"] = self.format_reasoning_log()
        self.match_log["human_reasoning_log"] = self.format_human_reasoning_log()
        self.match_log["llm_stats"] = self.llm_stats.summarize(self.hand_number)
            
        return self.match_log
        
    def play_hand(self) -> dict[str, Any]:
        
        if self.is_finished:
            raise RuntimeError("Cannot play hand: tournament is already finished.")
        
        self.hand_number += 1
        self.state = self.create_state()
        
        player_labels = {
            local_index: f"P{global_id}"
            for local_index, global_id in enumerate(self.current_hand_player_ids)
        }
        
        logger = HandLogger(
            hand_number = self.hand_number,
            state = self.state,
            reveal_hole_cards = self.reveal_hole_cards,
            include_legal_actions = self.include_legal_actions_in_log,
            include_pokerkit_operations = self.include_pokerkit_operations,
            player_labels=player_labels,
            hand_seed=self._compute_hand_seed()
        )
        
        step = 0
        safety_counter = 0
        max_steps = 500
        
        while self.state.status:
            safety_counter += 1
            
            if safety_counter > max_steps:
                raise RuntimeError(f"Exceeded maximum steps ({max_steps}) in hand #{self.hand_number}. Possible infinite loop.")
            
            legal_actions = get_legal_actions(self.state)
            
            if not legal_actions:
                print("No legal actions available. Ending hand.")
                break
            
            local_actor_index = self.state.actor_index
            player = self.current_hand_players[local_actor_index]
            agent = player.agent
            
            public_state = serialize_state_for_player(self.state, local_actor_index)
            public_state["state"]["global_player_id"] = player.global_id
            public_state["state"]["local_to_global_player_ids"] = self.current_hand_player_ids  
            
            if is_pokerbots_agent(agent):
                pokerbots_valid_actions = to_pokerbots_valid_actions(self.state)
                pb_action_name, pb_amount = agent.play(pokerbots_valid_actions, self.state)
                raw_action = from_pokerbots_action(self.state, pb_action_name, pb_amount)
            else:
                raw_action = agent.decide_action(public_state, legal_actions)
                
            decision_meta = None
            if hasattr(agent, "consume_last_decision_meta"):
                decision_meta = agent.consume_last_decision_meta()
                
            current_street = getattr(self.state, "street_index", None)
            street_name = {
                0: "preflop",
                1: "flop",
                2: "turn",
                3: "river",
            }.get(current_street, f"street_{current_street}")

            if decision_meta is not None:
                self.llm_stats.record(
                    hand_number=self.hand_number,
                    step=step,
                    street=street_name,
                    player_label=player_labels.get(local_actor_index, f"P{local_actor_index}"),
                    agent_name=agent.name,
                    decision_meta=decision_meta,
                )
                
            action = sanitize_action(raw_action, legal_actions)
            
            action_log_index = logger.before_action(
                step=step,
                state=self.state,
                actor_index=local_actor_index,
                agent_name=agent.name,
                legal_actions=legal_actions,
                raw_action=raw_action,
                applied_action=action,
                decision_meta=decision_meta
            )
            
            apply_action(self.state, action)
            
            logger.after_action(action_log_index, self.state)
            
            step += 1
            
        logger.finish(self.state)
        
        self._persist_hand_stacks()
        eliminations = self._eliminate_busted_players()
            
        result = self.result(logger, eliminations)
        
        self.match_log["hands"].append(
            {
                **result["hand_log"],
                "text_log": result["text_log"],
                "reasoning_log": logger.to_reasoning_dict(),
            }
        )
        self.match_log["eliminations"].extend(eliminations)
        
        if self.verbose:
            print(result["text_log"])
        
        return result
    
    def _persist_hand_stacks(self) -> None:
        for local_index, stack in enumerate(self.state.stacks):
            player = self.current_hand_players[local_index]
            player.stack = int(stack)
            
    def _eliminate_busted_players(self) -> list[dict[str, Any]]:
        eliminations: list[dict[str, Any]] = []
        
        for player in self.players:
            if player.eliminated:
                continue
            
            if player.stack <= 0:
                player.eliminated = True
                player.eliminated_hand = self.hand_number
                                
                eliminations.append(
                    {
                        "hand_number": self.hand_number,
                        "global_id": player.global_id,
                        "name": player.agent.name,
                    }
                )
        return eliminations
        
    def result(self, logger: HandLogger, eliminations: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "hand_seed": self._compute_hand_seed(),
            "hand_number": self.hand_number,
            "active_global_player_ids": self.current_hand_player_ids,
            "local_to_global_player_ids": self.current_hand_player_ids,
            "stacks": [int(x) for x in self.state.stacks],
            "global_stacks": {
                player.global_id: player.stack
                for player in self.players
            },
            "payoffs": [int(x) for x in self.state.payoffs],
            "board": logger.hand.final_board,
            "operations": [str(op) for op in self.state.operations],
            "eliminations": eliminations,
            "remaining_players": self.players_summary(active_only=True),
            "hand_log": logger.to_dict(),
            "text_log": logger.format_text(),
        }
        
    def players_summary(self, active_only: bool = False) -> list[dict[str, Any]]:
        players = self.active_players if active_only else self.players
        
        return [
            {
                "global_id": player.global_id,
                "name": player.agent.name,
                "stack": player.stack,
                "eliminated": player.eliminated,
                "eliminated_hand": player.eliminated_hand,
            }
            for player in players
        ]
        
    def format_match_summary(self) -> str:
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append("MATCH SUMMARY")
        lines.append("=" * 80)
        lines.append(f"Hands played: {self.hand_number}")
        lines.append("")
        
        lines.append("Players:")
        for player in self.players:
            status = "ELIMINATED" if player.eliminated else "ACTIVE"
            lines.append(f"- P{player.global_id} {player.agent.name}: Stack={player.stack}, Status={status}")
            
        lines.append("")
        
        if self.match_log["eliminations"]:
            lines.append("Eliminations:")
            for elimination in self.match_log["eliminations"]:
                lines.append(f"- Hand {elimination['hand_number']}: P{elimination['global_id']} {elimination['name']} eliminated")
            lines.append("")
            
        winner = self.winner
        if winner is not None:
            lines.append(f"Winner: P{winner.global_id} {winner.agent.name} with stack {winner.stack}")
        else:
            lines.append("No winner (all players busted or max hands reached)")
            
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def format_full_match_log(self) -> str:
        lines: list[str] = []
        
        for hand in self.match_log["hands"]:
            text_log = hand.get("text_log")
            if text_log:
                lines.append(text_log)
                lines.append("")
                
        lines.append(self.format_match_summary())
        
        return "\n".join(lines)
    
    def format_reasoning_log(self) -> dict[str, Any]:
        return {
            "hands": [
                hand["reasoning_log"]
                for hand in self.match_log["hands"]
                if "reasoning_log" in hand
            ]
        }
        
    def format_human_reasoning_log(self) -> str:
        lines: list[str] = []
        
        for hand in self.match_log.get("hands", []):
            reasoning_log = hand.get("reasoning_log")
            if not reasoning_log:
                continue
            
            hand_number = reasoning_log.get("hand_number")
            
            for action in reasoning_log.get("actions", []):
                own_hole_cards = action.get("own_hole_cards", [])
                board = action.get("board", [])
                applied_action = action.get("applied_action", {})
                decision_meta = action.get("decision_meta", {})
                
                action_taken = applied_action.get("type", "unknown")
                if action_taken in ["bet", "raise", "all_in"]:
                    action_taken = f"{action_taken} {applied_action.get('amount_to', '')}"
                elif action_taken == "call":
                    action_taken = f"call {applied_action.get('amount_to', '')}"
                    
                reasoning = decision_meta.get("response_thinking")
                motivation = action.get("motivation") or decision_meta.get("final_reason")
                
                player_stack = action.get("player_stack_before_action")
                player_bet = action.get("player_current_bet_before_action")
                pot_size = action.get("pot_size_before_action")
                
                lines.append("-" * 40)
                lines.append(f"Hand #{hand_number} - Turn {action.get('step')} - Street: {action.get('street')}")
                lines.append(f"Player: {action.get('player_label')} - Stack before action: {player_stack}")
                lines.append(f"Current bet before action: {player_bet} - Pot size before action: {pot_size}")
                lines.append(f"Current cards in hand: {', '.join(own_hole_cards) if own_hole_cards else '[]'}")
                lines.append(f"Current Board: {', '.join(board) if board else '[]'}")
                lines.append(f"Action taken: {action_taken}")
                lines.append(f"Reasoning: {reasoning if reasoning else 'N/A'}")
                lines.append(f"Motivation: {motivation if motivation else 'N/A'}")
                lines.append("-" * 40)
                lines.append("\n")

        return "\n".join(lines).strip()