import json
from typing import Any
import time

from ollama import chat, show

SYSTEM_PROMPT = """You are an action-selection engine for No-Limit Texas Hold'em.

Choose exactly one action from legal_actions.

Rules:
- Use only an action present in legal_actions.
- Never invent actions.
- If check is not explicitly present in legal_actions, then check is not allowed.
- If call is not explicitly present in legal_actions, then call is not allowed.
- If action is bet, raise, or all_in, use amount_to.
- amount_to must be within the allowed range.
- Never output text outside JSON.
- Keep reason short.
- Never assume hidden opponent cards.
- If uncertain, choose the safest reasonable legal action.

Return JSON only:
{
  "type": "fold|check|call|bet|raise|all_in",
  "amount_to": 0,
  "reason": "short explanation"
}"""

class OllamaAgent:
    def __init__(self, model: str, name: str = "OllamaAgent", host: str = "http://127.0.0.1:11434", temperature: float = 0.7, timeout: int = 120, think: bool | str = True):
        self.model = model
        self.name = name
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.think = think
        
        self.model_info = self._load_model_info()
        self.support_thinking = self._detect_thinking_support(self.model_info)
        
        self._last_decision_meta: dict[str, Any] | None = None
        
    def decide_action(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = self._build_prompt(public_state, legal_actions)
        
        self._last_decision_meta = {
            "agent_type": "ollama",
            "model": self.model,
            "prompt": prompt,
            "public_state": public_state,
            "legal_actions": legal_actions,
            "support_thinking": self.support_thinking,
            "requested_think": self.think,
            "thinking_enabled": self.support_thinking and bool(self.think),
            "response_content": None,
            "response_thinking": None,
            "parsed_action": None,
            "normalized_action": None,
            "fallback_used": False,
            "fallback_reason": None,
            "final_reason": None,
            "model_info": self.model_info,
        }
                
        chat_kwargs = {
            "model": self.model,
            "messages" : [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "format": "json",
            "options": {
                "temperature": self.temperature,
            },
        }
        
        if self.support_thinking and self.think not in (False, None):
            chat_kwargs["think"] = self.think
        
        start_time = time.perf_counter()
        try:
            response = chat(**chat_kwargs)
            end_time = time.perf_counter()
        except Exception as exc:
            end_time = time.perf_counter()
            self._last_decision_meta["fallback_used"] = True
            self._last_decision_meta["fallback_reason"] = f"Ollama error: {exc}"
            self._last_decision_meta["final_reason"] = f"Fallback due to Ollama error: {exc}"
            self._last_decision_meta["latency_seconds"] = end_time - start_time
            return self._fallback(legal_actions)
        
        content = response.message.content or ""
        thinking = getattr(response.message, "thinking", None)
        
        latency_seconds = end_time - start_time
        self._last_decision_meta["latency_seconds"] = latency_seconds
        self._last_decision_meta["prompt_eval_count"] = getattr(response, "prompt_eval_count", None)
        self._last_decision_meta["prompt_eval_duration_ns"] = getattr(response, "prompt_eval_duration", None)
        self._last_decision_meta["eval_count"] = getattr(response, "eval_count", None)
        self._last_decision_meta["eval_duration_ns"] = getattr(response, "eval_duration", None)
        self._last_decision_meta["total_duration_ns"] = getattr(response, "total_duration", None)
        self._last_decision_meta["load_duration_ns"] = getattr(response, "load_duration", None)
        
        eval_count = self._last_decision_meta["eval_count"]
        eval_duration_ns = self._last_decision_meta["eval_duration_ns"]
        
        if eval_count and eval_duration_ns and eval_duration_ns > 0:
            self._last_decision_meta["generation_tokens_per_second"] = (
                eval_count / (eval_duration_ns / 1_000_000_000)
            )
        else:
            self._last_decision_meta["generation_tokens_per_second"] = None
        
        self._last_decision_meta["response_content"] = content
        self._last_decision_meta["response_thinking"] = thinking
        
        try:
            action = json.loads(content)
            self._last_decision_meta["parsed_action"] = action
            self._last_decision_meta["raw_model_action_type"] = action.get("type")
            self._last_decision_meta["raw_model_amount_to"] = action.get("amount_to", action.get("amount"))
        except Exception as exc:
            self._last_decision_meta["fallback_used"] = True
            self._last_decision_meta["fallback_reason"] = f"invalid_json: {exc}"
            self._last_decision_meta["latency_seconds"] = latency_seconds
            self._last_decision_meta["illegal_action_returned"] = True
            return self._fallback(legal_actions)
        
        validated = self._validate_or_fallback(action, legal_actions)
        
        
        if validated != action:
            self._last_decision_meta["normalized_action"] = validated
        else:
            self._last_decision_meta["normalized_action"] = action
            
        reason = action.get("reason", "")
        if isinstance(reason, str) and reason.strip():
            self._last_decision_meta["final_reason"] = reason.strip()
        elif thinking:
            self._last_decision_meta["final_reason"] = thinking
        else:
            self._last_decision_meta["final_reason"] = "No reason provided"
            
        return validated
    
    def consume_last_decision_meta(self) -> dict[str, Any] | None:
        meta = self._last_decision_meta
        self._last_decision_meta = None
        return meta
    
    def _load_model_info(self) -> dict[str, Any]:
        try:
            info = show(self.model)
            capabilities = getattr(info, "capabilities", None)
            details = getattr(info, "details", None)
            
            return {
                "capabilities": list(capabilities) if capabilities else [],
                "details": details.model_dump() if hasattr(details, "model_dump") and details else None,
            }
        except Exception as exc:
            return {
                "capabilities": [],
                "details": None,
                "error": str(exc),
            }
            
    def _detect_thinking_support(self, model_info: dict[str, Any]) -> bool:
        capabilities = [str(x).lower() for x in model_info.get("capabilities", [])]
        
        if "thinking" in capabilities:
            return True
        
        model_lower = self.model.lower()
        thinking_markers = ["think", "thinking", "reasoning"]
        
        return any(marker in model_lower for marker in thinking_markers)
    
    def _build_prompt(self, public_state: dict[str, Any], legal_actions: list[dict[str, Any]]) -> str:
        legal_summary: list[str] = []
        
        for action in legal_actions:
            action_type = action.get("type")
            if action_type in {"fold", "check"}:
                legal_summary.append(f"- {action_type}")
            elif action_type == "call":
                legal_summary.append(f"- call amount={action.get('amount', 0)}")
            elif action_type in {"bet", "raise", "all_in"}:
                legal_summary.append(
                    f"- {action_type} amount_to between {action.get('min')} and {action.get('max')}"
                )
                        
        return f"""
Decide the next poker action.

You must choose exactly one action from legal_actions.

Valid choices summary:
{chr(10).join(legal_summary)}

Output format:
{{
  "type": "fold|check|call|bet|raise|all_in",
  "amount_to": 0,
  "reason": "short explanation"
}}

Game state JSON:
{json.dumps(public_state, ensure_ascii=False, indent=2)}

Legal actions JSON:
{json.dumps(legal_actions, ensure_ascii=False, indent=2)}

Important:
- Do not invent actions.
- If action is bet, raise, or all_in, use amount_to.
- Keep reason short.
- If your chosen action is not present in legal_actions, your answer is invalid.
- If multiple actions seem reasonable, prefer the simplest legal action.
- If unsure, choose check if available, otherwise call if available, otherwise fold.
- Return JSON only.
""".strip()


    def _validate_or_fallback(self, action: dict[str, Any], legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
        requested_type = action.get("type")
        
        for legal in legal_actions:
            if legal["type"] != requested_type:
                continue
            
            if requested_type in {"fold", "check", "call"}:
                self._last_decision_meta["illegal_action_returned"] = False
                return legal
            
            if requested_type in {"bet", "raise", "all_in"}:
                requested = int(action.get("amount_to", action.get("amount", legal.get("amount_to", legal.get("min", 0)))))
                self._last_decision_meta["illegal_action_returned"] = False
                return {
                    **legal,
                    "amount_to": max(int(legal["min"]), min(requested, int(legal["max"]))),
                }
                
        self._last_decision_meta["fallback_used"] = True
        self._last_decision_meta["illegal_action_returned"] = True
        self._last_decision_meta["fallback_reason"] = (
            f"illegal_action_not_in_legal_actions: requested={requested_type}, "
            f"legal={[a['type'] for a in legal_actions]}"
        )
        self._last_decision_meta["final_reason"] = action.get(
            "reason",
            "fallback because chosen action was not legal in this state",
        )
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
        
    