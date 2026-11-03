import os
from dataclasses import dataclass, field


@dataclass
class Completion:
    text: str
    refused: bool = False
    meta: dict = field(default_factory=dict)


class MockClient:
    def __init__(self, spec: dict):
        self.response = spec.get("response", "{}")

    def complete(self, system: str, user: str) -> Completion:
        return Completion(text=self.response)


class AnthropicClient:
    def __init__(self, spec: dict):
        import anthropic

        self.client = anthropic.Anthropic(max_retries=spec.get("max_retries", 6))
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
        meta = {"stop_reason": r.stop_reason}
        if r.stop_reason == "refusal" and getattr(r, "stop_details", None):
            meta["refusal_category"] = r.stop_details.category
        return Completion(text=text, refused=r.stop_reason == "refusal", meta=meta)


class GoogleClient:
    def __init__(self, spec: dict):
        from google import genai
        from google.genai import types

        self.client = genai.Client()
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
        return Completion(text=r.text or "", refused=refused, meta={"finish_reason": finish})


class OpenAICompatClient:
    def __init__(self, spec: dict):
        from openai import OpenAI

        key = os.environ.get(spec.get("api_key_env") or "", "") or "unused"
        self.client = OpenAI(base_url=spec["base_url"], api_key=key, max_retries=spec.get("max_retries", 6))
        self.model = spec["model"]
        self.params = spec.get("params", {})

    def complete(self, system: str, user: str) -> Completion:
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **self.params,
        )
        choice = r.choices[0]
        return Completion(
            text=choice.message.content or "",
            refused=choice.finish_reason == "content_filter",
            meta={"finish_reason": choice.finish_reason},
        )


PROVIDERS = {
    "anthropic": AnthropicClient,
    "google": GoogleClient,
    "openai_compat": OpenAICompatClient,
    "mock": MockClient,
}


def make_client(spec: dict):
    if spec["provider"] != "mock" and not spec.get("model"):
        raise ValueError("observer has no model set; run the `models` command and set `model` in the config")
    return PROVIDERS[spec["provider"]](spec)


def list_models(spec: dict) -> list[str]:
    provider = spec["provider"]
    if provider == "anthropic":
        import anthropic

        return [m.id for m in anthropic.Anthropic().models.list()]
    if provider == "google":
        from google import genai

        return [m.name for m in genai.Client().models.list()]
    if provider == "openai_compat":
        from openai import OpenAI

        key = os.environ.get(spec.get("api_key_env") or "", "") or "unused"
        return [m.id for m in OpenAI(base_url=spec["base_url"], api_key=key).models.list()]
    return []
