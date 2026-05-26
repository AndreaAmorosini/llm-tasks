import json
from typing import Any

from ollama import Client

class OllamaAgent:
    def __init__(self, model: str, name: str = "OllamaAgent", host: str = "http://127.0.0.1:11434", temperature: float = 0.7, timeout: int = 120, think: bool | str = True):
        self.model = model
        self.name = name
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.think = think
        self._last_decision_meta: dict[str, Any] | None = None
        
    def decide_action(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = self._build_prompt(public_state, legal_actions)
        
        self._last_decision_meta = {
            "agent_type": "ollama",
            "model": self.model,
            "prompt": prompt,
            "public_state": public_state,
            "legal_actions": legal_actions,
            "response_content": None,
            "response_thinking": None,
            "parsed_action": None,
            "fallback_used": False,
            "fallback_reason": None
        }
        
        try:
            response = self.client.chat(
                model = self.model,
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are a No-Limit Texas Hold'em poker player. "
                            "Choose exactly one legal action. "
                            "Do not invent actions. "
                            "Return only valid JSON. "
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                format = "json",
                think = self.think,
                options = {
                    "temperature": self.temperature,
                },
            )
        except Exception as exc:
            self._last_decision_meta["fallback_used"] = True
            self._last_decision_meta["fallback_reason"] = f"Ollama error: {exc}"
            return self._fallback(legal_actions)
        
        content = response.message.content or ""
        thinking = getattr(response.message, "thinking", None)
        
        self._last_decision_meta["response_content"] = content
        self._last_decision_meta["response_thinking"] = thinking
        
        try:
            action = json.loads(content)
            self._last_decision_meta["parsed_action"] = action
        except Exception as exc:
            self._last_decision_meta["fallback_used"] = True
            self._last_decision_meta["fallback_reason"] = f"invalid_json: {exc}"
            return self._fallback(legal_actions)
        
        validated = self._validate_or_fallback(action, legal_actions)
        
        if validated != action:
            self._last_decision_meta["normalized_action"] = validated
        else:
            self._last_decision_meta["normalized_action"] = action
            
        return validated
    
    def consume_last_decision_meta(self) -> dict[str, Any] | None:
        meta = self._last_decision_meta
        self._last_decision_meta = None
        return meta
    
    def _build_prompt(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> str:
        return json.dumps(
            {
                "instruction": (
                    "Choose one action from legal_actions. "
                    "For bet/raise/all_in use amount_to. "
                    "Return JSON only."
                ),
                "state": public_state,
                "legal_actions": legal_actions,
                "output_schema": {
                    "type": "fold|check|call|bet|raise|all_in",
                    "amount_to": "integer optional",
                    "reason": "short explanation optional",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        
    def _validate_or_fallback(self, action: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        requested_type = action.get("type")
        
        for legal in legal_actions:
            if legal["type"] != requested_type:
                continue
            
            if requested_type in {"fold", "check", "call"}:
                return legal
            
            if requested_type in {"bet", "raise", "all_in"}:
                requested = int(action.get("amount_to", action.get("amount", legal.get("amount_to", legal.get("min", 0)))))
                return {
                    **legal,
                    "amount_to": max(int(legal["min"]), min(requested, int(legal["max"]))),
                }
                
        self._last_decision_meta["fallback_used"] = True
        self._last_decision_meta["fallback_reason"] = f"invalid_action_type: {requested_type}"
        return self._fallback(legal_actions)
        
    def _fallback(self, legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        for action in legal_actions:
            if action["type"] == "check":
                return action
            
            if action["type"] == "call":
                return action
            
            if action["type"] == "fold":
                return action
            
        return legal_actions[0] if legal_actions else {"type": "fold"}
        
    