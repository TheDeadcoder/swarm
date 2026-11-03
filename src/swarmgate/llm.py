import os
from dataclasses import dataclass, field

TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
TRANSIENT_NAMES = ("connection", "timeout", "timedout", "unavailable", "disconnected", "temporar")


@dataclass
class Completion:
    text: str
    refused: bool = False
    meta: dict = field(default_factory=dict)


def _status(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def is_transient(exc: Exception) -> bool:
    status = _status(exc)
    if status is not None:
        return status in TRANSIENT_STATUS or status >= 500
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    name = type(exc).__name__.lower()
    return any(s in name for s in TRANSIENT_NAMES)


def retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = headers.get("retry-after") if headers is not None else None
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _key(spec: dict) -> str:
    return os.environ.get(spec.get("api_key_env") or "", "") or "unused"


class MockClient:
    def __init__(self, spec: dict):
        self.response = spec.get("response", "{}")

    def complete(self, system: str, user: str) -> Completion:
        return Completion(text=self.response)


class AnthropicClient:
    def __init__(self, spec: dict):
        import anthropic

        self.client = anthropic.Anthropic(max_retries=spec.get("sdk_retries", 2), timeout=spec.get("timeout", 600))
        self.model = spec["model"]
        self.effort = spec.get("effort")
        self.max_tokens = spec.get("max_tokens", 16000)

    def complete(self, system: str, user: str) -> Completion:
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        r = self.client.messages.create(**kwargs)
        text = "".join(b.text for b in r.content if b.type == "text")
        meta = {"stop_reason": r.stop_reason, "usage": {"input": r.usage.input_tokens, "output": r.usage.output_tokens}}
        if r.stop_reason == "refusal" and getattr(r, "stop_details", None):
            meta["refusal_category"] = r.stop_details.category
        return Completion(text=text, refused=r.stop_reason == "refusal", meta=meta)


def _genai_client(spec: dict):
    from google import genai

    if spec.get("vertexai"):
        return genai.Client(
            vertexai=True,
            project=os.environ.get(spec.get("project_env", "GOOGLE_CLOUD_PROJECT")),
            location=spec.get("location", "global"),
        )
    return genai.Client()


class GoogleClient:
    def __init__(self, spec: dict):
        from google.genai import types

        self.client = _genai_client(spec)
        self.types = types
        self.model = spec["model"]

    def complete(self, system: str, user: str) -> Completion:
        r = self.client.models.generate_content(
            model=self.model,
            contents=user,
            config=self.types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json"),
        )
        finish = str(r.candidates[0].finish_reason) if r.candidates else None
        blocked = getattr(getattr(r, "prompt_feedback", None), "block_reason", None)
        refused = bool(blocked) or (finish is not None and "SAFETY" in finish)
        u = r.usage_metadata
        usage = {
            "input": getattr(u, "prompt_token_count", 0) or 0,
            "output": (getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0),
        }
        return Completion(text=r.text or "", refused=refused, meta={"finish_reason": finish, "usage": usage})


class OpenAICompatClient:
    def __init__(self, spec: dict):
        from openai import OpenAI

        self.client = OpenAI(
            base_url=spec["base_url"], api_key=_key(spec), max_retries=spec.get("sdk_retries", 2), timeout=spec.get("timeout", 600)
        )
        self.model = spec["model"]
        self.params = spec.get("params", {})

    def complete(self, system: str, user: str) -> Completion:
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **self.params,
        )
        choice = r.choices[0]
        usage = {"input": r.usage.prompt_tokens, "output": r.usage.completion_tokens} if r.usage else {}
        return Completion(
            text=choice.message.content or "",
            refused=choice.finish_reason == "content_filter",
            meta={"finish_reason": choice.finish_reason, "usage": usage},
        )


PROVIDERS = {
    "anthropic": AnthropicClient,
    "google": GoogleClient,
    "openai_compat": OpenAICompatClient,
    "mock": MockClient,
}


def make_client(spec: dict):
    if spec["provider"] != "mock" and not spec.get("model"):
        raise ValueError("observer has no model set; run the `models` command and set `model` in the observers file")
    return PROVIDERS[spec["provider"]](spec)


def list_models(spec: dict) -> list[str]:
    provider = spec["provider"]
    if provider == "anthropic":
        import anthropic

        return [m.id for m in anthropic.Anthropic().models.list()]
    if provider == "google":
        return [m.name for m in _genai_client(spec).models.list()]
    if provider == "openai_compat":
        from openai import OpenAI

        return [m.id for m in OpenAI(base_url=spec["base_url"], api_key=_key(spec)).models.list()]
    return []
