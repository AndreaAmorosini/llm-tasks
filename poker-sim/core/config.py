from dataclasses import dataclass

@dataclass(frozen=True)
class GameConfig:
    player_count: int = 4
    starting_stack: int = 1_000
    small_blind: int = 5
    big_blind: int = 10
    ante: int = 0
    min_bet: int = 10
    max_hands: int | None = 1_000
    
    @property
    def blinds(self) -> tuple[int, int]:
        return self.small_blind, self.big_blind
    
    @property
    def starting_stacks(self) -> tuple[int, ...]:
        return tuple([self.starting_stack] * self.player_count)