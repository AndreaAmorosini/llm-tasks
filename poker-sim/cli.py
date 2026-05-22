import argparse
import json

from agents.random_agent import RandomAgent
from agents.rule_agent import TightPassiveAgent
from core.config import GameConfig
from core.game import PokerGame


def build_agents(kind: str, player_count: int):
    if kind == "random":
        return [RandomAgent(name=f"Random_{i}") for i in range(player_count)]

    if kind == "tight":
        return [TightPassiveAgent(name=f"Tight_{i}") for i in range(player_count)]

    if kind == "mixed":
        agents = []

        for i in range(player_count):
            if i % 2 == 0:
                agents.append(RandomAgent(name=f"Random_{i}"))
            else:
                agents.append(TightPassiveAgent(name=f"Tight_{i}"))

        return agents

    raise ValueError(f"Unknown agent kind: {kind}")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--hands", type=int, default=1)
    parser.add_argument("--stack", type=int, default=1000)
    parser.add_argument("--sb", type=int, default=5)
    parser.add_argument("--bb", type=int, default=10)
    parser.add_argument("--ante", type=int, default=0)

    parser.add_argument(
        "--agents",
        choices=["random", "tight", "mixed"],
        default="mixed",
    )

    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")

    parser.add_argument(
        "--hide-hole-cards",
        action="store_true",
        help="Non mostrare le carte private dei player nel log finale.",
    )

    parser.add_argument(
        "--log-legal-actions",
        action="store_true",
        help="Include tutte le legal actions disponibili nel log JSON.",
    )

    parser.add_argument(
        "--log-pokerkit-operations",
        action="store_true",
        help="Include anche le operations interne di PokerKit.",
    )

    args = parser.parse_args()

    config = GameConfig(
        player_count=args.players,
        starting_stack=args.stack,
        small_blind=args.sb,
        big_blind=args.bb,
        ante=args.ante,
        min_bet=args.bb,
    )

    agents = build_agents(args.agents, args.players)

    game = PokerGame(
        config=config,
        agents=agents,
        verbose=args.verbose,
        reveal_hole_cards=not args.hide_hole_cards,
        include_legal_actions_in_log=args.log_legal_actions,
        include_pokerkit_operations=args.log_pokerkit_operations,
    )

    results = game.play_hands(args.hands)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    if not args.verbose:
        for result in results:
            print(result["text_log"])

    final = results[-1]

    print()
    print(f"Mani giocate: {args.hands}")
    print(f"Stacks finali ultima mano: {final['stacks']}")
    print(f"Payoffs ultima mano: {final['payoffs']}")


if __name__ == "__main__":
    main()