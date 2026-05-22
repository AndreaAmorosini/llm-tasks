from typing import Any
from pokerkit import Automation, Mode, NoLimitTexasHoldem
from agents.base import Agent
from core.action_mapper import apply_action, get_legal_actions, sanitize_action
from core.config import GameConfig
from core.hand_logger import HandLogger
from core.state_serializer import serialize_state_for_player

class PokerGame:
    def __init__(self, config: GameConfig, agents: list[Agent], verbose: bool = False, reveal_hole_cards: bool = False, include_legal_actions_in_log: bool = False, include_pokerkit_operations: bool = False):
        if len(agents) != config.player_count:
            raise ValueError(f"Number of agents ({len(agents)}) must match player count in config ({config.player_count})")
        
        self.config = config
        self.agents = agents
        self.verbose = verbose
        self.reveal_hole_cards = reveal_hole_cards
        self.include_legal_actions_in_log = include_legal_actions_in_log
        self.include_pokerkit_operations = include_pokerkit_operations
        
        self.state = None
        self.hand_number = 0
        self.hand_logs: list[dict[str, Any]] = []
        
    def create_state(self):
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
            self.config.starting_stacks,
            self.config.player_count,
            mode = Mode.CASH_GAME
        )
        
    def play_hand(self) -> dict[str, Any]:
        self.hand_number += 1
        self.state = self.create_state()
        
        logger = HandLogger(
            hand_number = self.hand_number,
            state = self.state,
            reveal_hole_cards = self.reveal_hole_cards,
            include_legal_actions = self.include_legal_actions_in_log,
            include_pokerkit_operations = self.include_pokerkit_operations
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
                self._log("No legal actions available. Ending hand.")
                break
            
            actor_index = self.state.actor_index
            agent = self.agents[actor_index]
            
            public_state = serialize_state_for_player(self.state, actor_index)
            raw_action = agent.decide_action(public_state, legal_actions)
            action = sanitize_action(raw_action, legal_actions)
            
            action_log_index = logger.before_action(
                step=step,
                state=self.state,
                actor_index=actor_index,
                agent_name=agent.name,
                legal_actions=legal_actions,
                raw_action=raw_action,
                applied_action=action
            )
            
            apply_action(self.state, action)
            
            logger.after_action(action_log_index, self.state)
            
            step += 1
            
        logger.finish(self.state)
            
        result = self.result(logger)
        
        self.hand_logs.append(result["hand_log"])
        
        if self.verbose:
            print(result["text_log"])
        
        return result
    
    def play_hands(self, count: int) -> list[dict[str, Any]]:
        return [self.play_hand() for _ in range(count)]
    
    def result(self, logger: HandLogger) -> dict[str, Any]:
        return {
            "hand_number": self.hand_number,
            "stacks": [int(x) for x in self.state.stacks],
            "payoffs": [int(x) for x in self.state.payoffs],
            "board": [str(card) for card in getattr(self.state, "board_cards", [])],
            "operations": [str(op) for op in self.state.operations],
            "hand_log": logger.to_dict(),
            "text_log": logger.format_text(),
        }
        
    def _log_action(self, actor_index: int, agent_name: str, action: dict[str, Any]) -> None:
        action_type = action["type"]
        
        if action_type in {"bet", "raise", "all_in"}:
            msg = f"P{actor_index} {agent_name}: {action_type} to {action['amount_to']}"
        elif action_type == "call":
            msg = f"P{actor_index} {agent_name}: call {action.get('amount', 0)}"
        else:
            msg = f"P{actor_index} {agent_name}: {action_type}"
            
    def _log(self, message: str) -> None:
        self.log.append(message)
        
        if self.verbose:
            print(message)