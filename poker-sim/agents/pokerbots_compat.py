# Adapted from Skripkon/PokerBots (MIT License)
# https://github.com/Skripkon/PokerBots

from __future__ import annotations
import random
import treys

class PokerBotsBasePlayer:
    def __init__(self, name: str = "NPC"):
        self.name = name
        
    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        raise NotImplementedError
    
class CallingPlayer(PokerBotsBasePlayer):
    #Check if valid, otherwise call
    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        return "check_or_call", float(valid_actions["check_or_call"])
    
class RandomPlayer(PokerBotsBasePlayer):
    #Random action
    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        possible_actions = ["check_or_call", "fold"]
        
        if "complete_bet_or_raise_to" in valid_actions:
            possible_actions.append("complete_bet_or_raise_to")
            
        action = random.choice(possible_actions)
        
        if action == "fold" and valid_actions.get("check_or_call") == 0:
            return "check_or_call", 0.0
        
        if action == "complete_bet_or_raise_to":
            min_to, max_to = valid_actions[action]
            amount = random.randint(min_to, max_to)
            return action, float(amount)
        
        return action, float(valid_actions[action])
    
class GamblingPlayer(PokerBotsBasePlayer):
    #Monte Carlo Simulation
    def __init__(self, name: str = "NPC", win_rate_threshold: float = 0.90, n_simulations: int = 100):
        super().__init__(name)
        self.win_rate_threshold = win_rate_threshold
        self.n_simulations = n_simulations
        
        self._deck = [
            treys.Card.new(card)
            for card in (
                "2c", "2d", "2h", "2s",
                "3c", "3d", "3h", "3s",
                "4c", "4d", "4h", "4s",
                "5c", "5d", "5h", "5s",
                "6c", "6d", "6h", "6s",
                "7c", "7d", "7h", "7s",
                "8c", "8d", "8h", "8s",
                "9c", "9d", "9h", "9s",
                "Tc", "Td", "Th", "Ts",
                "Jc", "Jd", "Jh", "Js",
                "Qc", "Qd", "Qh", "Qs",
                "Kc", "Kd", "Kh", "Ks",
                "Ac", "Ad", "Ah", "As",
            )
        ]
        
    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        if "complete_bet_or_raise_to" in valid_actions:
            hole_cards = self._flatten_cards(list(state.hole_cards[state.actor_index]))
            board_cards = self._extract_board_cards(state)
            n_players = self._count_active_players(state)
            
            win_rate = self._compute_win_rate(
                hole_cards = hole_cards,
                board_cards = board_cards,
                n_players = n_players,
                n_simulations = self.n_simulations
            )
            
            if win_rate >= self.win_rate_threshold:
                _, max_to = valid_actions["complete_bet_or_raise_to"]
                return "complete_bet_or_raise_to", float(max_to)
            
        if valid_actions.get("check_or_call", 0) == 0:
            return "check_or_call", 0.0
        
        return "fold", 0.0
    
    def _extract_board_cards(self, state) -> list[int]:
        try:
            cards: list = []
            if hasattr(state, "board_indices") and hasattr(state, "get_board"):
                for board_index in state.board_indices:
                    cards.extend(state.get_board(board_index))
                return cards
            return self._flatten_cards(getattr(state, "board_cards", []))
        except Exception:
            return list(getattr(state, "board_cards", []))
        
    def _flatten_cards(self, items) -> list:
        flat: list = []
        
        if items is None:
            return flat
        
        for item in items:
            if isinstance(item, (list, tuple)):
                flat.extend(self._flatten_cards(item))
            else:
                flat.append(item)
        
        return flat
        
    def _count_active_players(self, state) -> int:
        try:
            return sum(1 for status in state.statuses if status)
        except Exception:
            return int(getattr(state, "player_count", 2))
        
    def _to_treys_card(self, card) -> int:
        rank = str(card.rank)
        suit = getattr(card.suit, "value", str(card.suit))
        return treys.Card.new(f"{rank}{suit}")
    
    def _compute_win_rate(
        self, hole_cards: list,
        board_cards: list,
        n_players: int,
        n_simulations: int
    ) -> float:
        evaluator = treys.Evaluator()
        deck = self._deck.copy()
        
        hero = [self._to_treys_card(card) for card in hole_cards]
        board = [self._to_treys_card(card) for card in board_cards]
        
        for card in hero + board:
            if card in deck:
                deck.remove(card)
                
        wins = 0
        
        for _ in range(n_simulations):
            missing_board = 5 - len(board)
            needed_cards = missing_board + 2 * (n_players - 1)
            sampled = random.sample(deck, needed_cards)
            
            simulated_board = board + sampled[:missing_board]
            hero_score = evaluator.evaluate(hand=hero, board=simulated_board)
            
            best = True
            offset = missing_board
            
            for i in range(n_players - 1):
                enemy_hole = sampled[offset + i*2 : offset + i*2 + 2]
                enemy_score = evaluator.evaluate(hand=enemy_hole, board=simulated_board)
                
                if enemy_score < hero_score:
                    best = False
                    break
            
            if best:
                wins += 1
                
        return wins / n_simulations
