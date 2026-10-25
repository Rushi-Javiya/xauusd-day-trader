"""LLM access. The model explains and researches; it never sizes, plans or sends orders.

`LLM` is a tiny interface so tests can inject a scripted fake and no API call is ever needed in CI."""
import os
from typing import Optional, Protocol


class LLM(Protocol):
    async def complete(self, system: str, prompt: str, *, web_search: bool = False) -> str: ...


def load_env_file(path: str = ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding variables that are already set."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def text_of(content) -> str:
    """Join the text blocks of an Anthropic message (ignores tool-use and search-result blocks)."""
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


class ClaudeLLM:
    def __init__(self, model: str = "claude-haiku-5-5", news_model: str = "claude-sonnet-5-5",
                 max_tokens: int = 1500):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set (put it in .env or the environment)")
        self.model, self.news_model, self.max_tokens = model, news_model, max_tokens

    async def complete(self, system: str, prompt: str, *, web_search: bool = False) -> str:
        from langchain_anthropic import ChatAnthropic
        chat = ChatAnthropic(model=self.news_model if web_search else self.model, max_tokens=self.max_tokens)
        if web_search:
            chat = chat.bind_tools([{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}])
        msg = await chat.ainvoke([("system", system), ("human", prompt)])
        return text_of(msg.content).strip()


class ScriptedLLM:
    """Test double: returns canned replies in order (the last one repeats) and records every call."""

    def __init__(self, *replies: str, error: Optional[Exception] = None):
        self.replies, self.error, self.calls = list(replies), error, []

    async def complete(self, system: str, prompt: str, *, web_search: bool = False) -> str:
        self.calls.append({"system": system, "prompt": prompt, "web_search": web_search})
        if self.error:
            raise self.error
        return self.replies.pop(0) if len(self.replies) > 1 else (self.replies[0] if self.replies else "")
