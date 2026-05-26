import argparse
import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime


from agents.random_agent import RandomAgent
from agents.rule_agent import TightPassiveAgent
from core.config import GameConfig
from core.game import PokerGame

from agents.pokerbots_compat import (
    CallingPlayer,
    GamblingPlayer,
    RandomPlayer as PokerBotsRandomPlayer
)

from agents.ollama_agent import OllamaAgent


def load_env_file(path: str | Path) -> None:
    env_path = Path(path)
    
    if not env_path.exists():
        return
    
    for line in env_path.read_text().splitlines():
        line = line.strip()
        
        if not line or line.startswith("#"):
            continue
        
        if "=" not in line:
            continue
        
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        
        os.environ.setdefault(key, value)
        
def env_str(name: str, default: str) -> str:
    return os.getenv(name, default)

def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got: {value}")
    
def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    
    if value is None or value == "":
        return default
    
    return value.lower() in ("1", "true", "yes", "y", "on")

def env_optional_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    
    if value is None or value == "":
        return default
    
    if value.lower() in {"none", "null", "unlimited", "infinite", "until_winner"}:
            return None

    return int(value)

def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    
    return float(value)

def build_agents(kind: str, player_count: int, ollama_model: str, ollama_host: str, ollama_temperature: float, ollama_timeout: int, ollama_think: bool | str):
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
    
    if kind == "pokerbots-random":
        return [PokerBotsRandomPlayer(name=f"PB_Random{i}") for i in range(player_count)]
    
    if kind == "pokerbots-calling":
        return [CallingPlayer(name=f"PB_Calling{i}") for i in range(player_count)]
    
    if kind == "pokerbots-gambling":
        return [GamblingPlayer(name=f"PB_Gambling{i}") for i in range(player_count)]
    
    if kind == "mixed-pokerbots":
        classes = [PokerBotsRandomPlayer, CallingPlayer, GamblingPlayer]
        return [classes[i % len(classes)](name=f"{classes[i % len(classes)].__name__}_{i}") for i in range(player_count)]
    
    if kind == "ollama-vs":
        agents = []
        agents.append(OllamaAgent(
            model=ollama_model,
            name=f"Ollama_{ollama_model}",
            host=ollama_host,
            temperature=ollama_temperature,
            timeout=ollama_timeout,
            think=ollama_think
        ))
        
        agents.append(GamblingPlayer(name="PB_Gambling"))
        agents.append(CallingPlayer(name="PB_Calling"))
        agents.append(PokerBotsRandomPlayer(name="PB_Random"))
        
        return agents
        


    raise ValueError(f"Unknown agent kind: {kind}")

def export_match_results(match_result: dict, export_dir: str | Path) -> Path:
    base_dir = Path(export_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    match_dir = base_dir / f"match_{timestamp}"
    
    match_dir.mkdir(parents=True, exist_ok=True)
    
    terminal_log_path = match_dir / "terminal_log.txt"
    json_log_path = match_dir / "match_result.json"
    reasoning_log_path = match_dir / "reasoning_log.json"

    terminal_log = match_result.get("match_text_log", "")
    terminal_log_path.write_text(terminal_log, encoding="utf-8")
    
    json_log_path.write_text(
        json.dumps(match_result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    reasoning_log = match_result.get("reasoning_log", {"hands": []})
    reasoning_log_path.write_text(
        json.dumps(reasoning_log, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    return match_dir

def parse_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=".env")

    pre_args, remaining = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)
        
    parser = argparse.ArgumentParser(
        parents=[pre_parser],
        description="Texas Hold'em simulator powered by PokerKit.",
    )

    parser.add_argument("--players", type=int, default=env_int("POKER_PLAYERS", 4))
    parser.add_argument("--hands", type=int, default=env_optional_int("POKER_HANDS", 1))
    parser.add_argument("--stack", type=int, default=env_int("POKER_STACK", 1000))
    parser.add_argument("--sb", type=int, default=env_int("POKER_SMALL_BLIND", 5))
    parser.add_argument("--bb", type=int, default=env_int("POKER_BIG_BLIND", 10))
    parser.add_argument("--ante", type=int, default=env_int("POKER_ANTE", 0))

    parser.add_argument(
        "--agents",
        choices=["random", "tight", "mixed", "pokerbots-random", "pokerbots-calling", "pokerbots-gambling", "mixed-pokerbots", "ollama-vs"],
        default=env_str("POKER_AGENTS", "mixed"),
    )
    
    parser.add_argument(
        "--ollama-model",
        default=env_str("OLLAMA_MODEL", "qwen3:4b"),
    )

    parser.add_argument(
        "--ollama-host",
        default=env_str("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )

    parser.add_argument(
        "--ollama-temperature",
        type=float,
        default=env_float("OLLAMA_TEMPERATURE", 0.2),
    )

    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=env_int("OLLAMA_TIMEOUT", 120),
    )

    parser.add_argument(
        "--ollama-think",
        default=env_str("OLLAMA_THINK", "true"),
        help="true|false|low|medium|high",
    )

    parser.add_argument(
        "--until-winner",
        action="store_true",
        default=env_bool("POKER_UNTIL_WINNER", False),
        help="Continua la partita finché resta un solo player.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=env_bool("POKER_VERBOSE", False),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        default=env_bool("POKER_JSON", False),
    )
    
    parser.add_argument(
        "--export",
        action="store_true",
        default=env_bool("POKER_EXPORT", False),
        help="Esporta un file JSON con il log completo di ogni mano e azione.",
    )
    
    parser.add_argument(
        "--export-dir",
        default=env_str("POKER_EXPORT_DIR", "exports"),
        help="Directory dove esportare i log delle partite (usato solo se --export è attivo).",
    )

    parser.add_argument(
        "--hide-hole-cards",
        action="store_true",
        default=env_bool("POKER_HIDE_HOLE_CARDS", False),
        help="Non mostrare le carte private dei player nel log finale.",
    )

    parser.add_argument(
        "--log-legal-actions",
        action="store_true",
        default=env_bool("POKER_LOG_LEGAL_ACTIONS", False),
        help="Include tutte le legal actions disponibili nel log JSON.",
    )

    parser.add_argument(
        "--log-pokerkit-operations",
        action="store_true",
        default=env_bool("POKER_LOG_POKERKIT_OPERATIONS", False),
        help="Include anche le operations interne di PokerKit.",
    )

    return parser.parse_args(remaining)

def parse_ollama_think(value: str) -> bool | str:
    lowered = value.lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    if lowered in {"low", "medium", "high"}:
        return lowered
    raise ValueError(f"Invalid OLLAMA_THINK value: {value}")

def main() -> None:
    args = parse_args()
            
    max_hands = None if args.until_winner else args.hands

    config = GameConfig(
        player_count=args.players,
        starting_stack=args.stack,
        small_blind=args.sb,
        big_blind=args.bb,
        ante=args.ante,
        min_bet=args.bb,
        max_hands=max_hands
    )

    # agents = build_agents(args.agents, args.players)
    agents = build_agents(
        kind=args.agents,
        player_count=args.players,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
        ollama_temperature=args.ollama_temperature,
        ollama_timeout=args.ollama_timeout,
        ollama_think=parse_ollama_think(args.ollama_think),
    )

    game = PokerGame(
        config=config,
        agents=agents,
        verbose=args.verbose,
        reveal_hole_cards=not args.hide_hole_cards,
        include_legal_actions_in_log=args.log_legal_actions,
        include_pokerkit_operations=args.log_pokerkit_operations,
    )

    match_result = game.play_match(max_hands=max_hands)
    
    if args.export:
        export_path = export_match_results(match_result, args.export_dir)
        print(f"Match results exported to: {export_path}")

    if args.json:
        print(json.dumps(match_result, indent=2))
        return

    print()
    print(f"Mani giocate: {match_result['hands_played']}")
    print(f"Partita finita: {match_result['finished']}")
    print(f"Winner: {match_result['winner']}")
    print("Player finali:")
    for player in match_result["final_players"]:
        print(player)


if __name__ == "__main__":
    main()