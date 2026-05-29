# Adapted from Skripkon/PokerBots (MIT License)
# https://github.com/Skripkon/PokerBots

from __future__ import annotations

import random

import treys


class PokerBotsBasePlayer:
    def __init__(self, name: str = "NPC", rng: random.Random | None = None):
        self.name = name
        self.rng = rng or random.Random()

    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        raise NotImplementedError


class CallingPlayer(PokerBotsBasePlayer):
    # Check if valid, otherwise call.
    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        return "check_or_call", float(valid_actions["check_or_call"])


class RandomPlayer(PokerBotsBasePlayer):
    # Random action.
    def play(self, valid_actions: dict[str, object], state) -> tuple[str, float]:
        possible_actions = ["check_or_call", "fold"]

        if "complete_bet_or_raise_to" in valid_actions:
            possible_actions.append("complete_bet_or_raise_to")

        action = self.rng.choice(possible_actions)

        if action == "fold" and valid_actions.get("check_or_call") == 0:
            return "check_or_call", 0.0

        if action == "complete_bet_or_raise_to":
            min_to, max_to = valid_actions[action]
            amount = self.rng.randint(int(min_to), int(max_to))
            return action, float(amount)

        return action, float(valid_actions[action])


class GamblingPlayer(PokerBotsBasePlayer):
    """
    Monte Carlo poker bot.

    Previous behavior was intentionally very tight:
    - raise all-in/max only above a fixed 90% win-rate threshold;
    - otherwise check if free;
    - otherwise fold.

    This version is more robust against aggressive/LLM opponents:
    - estimates hand equity with Monte Carlo;
    - calls using pot odds;
    - raises for value with reasonable sizing;
    - does not auto-fold every non-nut hand;
    - counts split pots as partial equity.
    """

    def __init__(
        self,
        name: str = "NPC",
        win_rate_threshold: float = 0.60,
        n_simulations: int = 500,
        rng: random.Random | None = None,
        raise_threshold: float | None = None,
        value_bet_threshold: float = 0.58,
        call_margin: float = 0.03,
        bluff_frequency: float = 0.04,
    ):
        super().__init__(name=name, rng=rng)

        # Kept for backward compatibility with the previous constructor.
        self.win_rate_threshold = win_rate_threshold

        self.raise_threshold = (
            raise_threshold if raise_threshold is not None else win_rate_threshold
        )
        self.value_bet_threshold = value_bet_threshold
        self.call_margin = call_margin
        self.bluff_frequency = bluff_frequency
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
        call_amount = float(valid_actions.get("check_or_call", 0) or 0)
        can_raise = "complete_bet_or_raise_to" in valid_actions

        hole_cards = self._flatten_cards(list(state.hole_cards[state.actor_index]))
        board_cards = self._extract_board_cards(state)
        n_players = self._count_active_players(state)

        win_rate = self._compute_win_rate(
            hole_cards=hole_cards,
            board_cards=board_cards,
            n_players=n_players,
            n_simulations=self.n_simulations,
        )

        # If checking is free, never fold.
        # Value-bet strong hands instead of passively checking everything.
        if call_amount == 0:
            if can_raise and win_rate >= self.value_bet_threshold:
                min_to, max_to = valid_actions["complete_bet_or_raise_to"]
                amount = self._choose_raise_amount(
                    state=state,
                    min_to=int(min_to),
                    max_to=int(max_to),
                    win_rate=win_rate,
                )
                return "complete_bet_or_raise_to", float(amount)

            # Rare bluff/semi-bluff to avoid being completely predictable.
            if can_raise and self.rng.random() < self.bluff_frequency:
                min_to, max_to = valid_actions["complete_bet_or_raise_to"]
                return "complete_bet_or_raise_to", float(min_to)

            return "check_or_call", 0.0

        pot = float(getattr(state, "total_pot_amount", 0) or 0)
        pot_odds = call_amount / max(pot + call_amount, 1.0)

        # Raise for value when equity is clearly good.
        if can_raise and win_rate >= self.raise_threshold:
            min_to, max_to = valid_actions["complete_bet_or_raise_to"]
            amount = self._choose_raise_amount(
                state=state,
                min_to=int(min_to),
                max_to=int(max_to),
                win_rate=win_rate,
            )
            return "complete_bet_or_raise_to", float(amount)

        # Call when the hand has enough equity relative to the price.
        if win_rate >= pot_odds + self.call_margin:
            return "check_or_call", call_amount

        # Occasionally defend close spots against aggressive opponents.
        # This prevents LLM opponents from exploiting the bot with tiny frequent bets.
        close_spot = win_rate >= max(0.0, pot_odds - 0.02)
        cheap_call = pot > 0 and call_amount <= pot * 0.15

        if close_spot and cheap_call:
            return "check_or_call", call_amount

        return "fold", 0.0

    def _choose_raise_amount(
        self,
        state,
        min_to: int,
        max_to: int,
        win_rate: float,
    ) -> int:
        pot = int(getattr(state, "total_pot_amount", 0) or 0)

        if pot <= 0:
            return min_to

        if win_rate >= 0.85:
            target = int(pot * 1.75)
        elif win_rate >= 0.75:
            target = int(pot * 1.25)
        elif win_rate >= 0.65:
            target = int(pot * 0.85)
        else:
            target = int(pot * 0.60)

        return max(min_to, min(target, max_to))

    def _extract_board_cards(self, state) -> list:
        try:
            cards: list = []

            if hasattr(state, "board_indices") and hasattr(state, "get_board"):
                for board_index in state.board_indices:
                    cards.extend(self._flatten_cards(state.get_board(board_index)))
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
            return max(2, sum(1 for status in state.statuses if status))
        except Exception:
            return max(2, int(getattr(state, "player_count", 2)))

    def _to_treys_card(self, card) -> int:
        if isinstance(card, int):
            return card

        if isinstance(card, str):
            return treys.Card.new(card)

        rank = str(card.rank)
        suit = getattr(card.suit, "value", str(card.suit))

        return treys.Card.new(f"{rank}{suit}")

    def _compute_win_rate(
        self,
        hole_cards: list,
        board_cards: list,
        n_players: int,
        n_simulations: int,
    ) -> float:
        if n_simulations <= 0:
            return 0.0

        evaluator = treys.Evaluator()
        deck = self._deck.copy()

        hero = [self._to_treys_card(card) for card in hole_cards]
        board = [self._to_treys_card(card) for card in board_cards]

        for card in hero + board:
            if card in deck:
                deck.remove(card)

        missing_board = max(0, 5 - len(board))
        opponents = max(1, n_players - 1)
        needed_cards = missing_board + 2 * opponents

        if len(hero) != 2:
            return 0.0

        if needed_cards > len(deck):
            return 0.0

        equity = 0.0

        for _ in range(n_simulations):
            sampled = self.rng.sample(deck, needed_cards)

            simulated_board = board + sampled[:missing_board]
            hero_score = evaluator.evaluate(hand=hero, board=simulated_board)

            better_opponents = 0
            tied_opponents = 0

            offset = missing_board

            for i in range(opponents):
                enemy_hole = sampled[offset + i * 2: offset + i * 2 + 2]
                enemy_score = evaluator.evaluate(
                    hand=enemy_hole,
                    board=simulated_board,
                )

                # In treys, lower score means stronger hand.
                if enemy_score < hero_score:
                    better_opponents += 1
                    break

                if enemy_score == hero_score:
                    tied_opponents += 1

            if better_opponents == 0:
                equity += 1.0 / (tied_opponents + 1)

        return equity / n_simulations