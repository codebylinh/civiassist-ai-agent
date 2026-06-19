"""
Unified LLM interface — wraps Groq so all other modules stay provider-agnostic.
"""
import json
from groq import Groq
import config

_client: Groq | None = None


def _get() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def complete(messages: list[dict], max_tokens: int = 1024,
             temperature: float = 0.7) -> str:
    """Single-turn completion — returns text only."""
    resp = _get().chat.completions.create(
        model=config.MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, list[dict]]:
    """
    One round of tool-capable chat.
    Returns (text, tool_calls) where each tool_call is
    {"id": str, "name": str, "arguments": dict}.
    """
    resp = _get().chat.completions.create(
        model=config.MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=max_tokens,
        temperature=temperature,
    )
    msg = resp.choices[0].message
    text = msg.content or ""
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
    return text, tool_calls


def assistant_tool_message(text: str, tool_calls: list[dict]) -> dict:
    """Build the assistant message dict for a turn that used tools."""
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"]),
                },
            }
            for tc in tool_calls
        ],
    }


def tool_result_message(tool_call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}
