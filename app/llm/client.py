"""Provider-agnostic LLM facade backed by Google Gemini (official SDK).

Design rules baked in here:

* One central quota manager (``app.llm.quota``) gates every request.
* Manual function calling only. The SDK's automatic loop is disabled so the
  application decides which tools run and can audit them.
* Structured output uses a JSON schema plus exactly one repair retry.
* 429 / quota errors degrade gracefully; nothing retries in a tight loop.
* API keys are never logged and never reach the browser.
* Callers pass already minimised payloads. This layer never adds profile
  contact details to a prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from google import genai
from google.genai import types

from app.config import settings
from app.llm.quota import QuotaExceeded, quota

log = logging.getLogger(__name__)

# Hard ceilings so a runaway prompt cannot burn the free tier.
MAX_TOOL_STEPS = 6
MAX_OUTPUT_TOKENS = 2048
DEFAULT_TIMEOUT = 45.0


class LlmError(RuntimeError):
    """Recoverable provider error."""


class LlmUnavailable(LlmError):
    """No key configured, or the provider is unreachable."""


class LlmQuotaError(LlmError):
    """Free-tier quota exhausted or per-user budget reached."""

    def __init__(self, reason: str, reset_at=None, slot: str = "fast"):
        super().__init__(reason)
        self.reason = reason
        self.reset_at = reset_at
        self.slot = slot


@dataclass
class LlmUsage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @property
    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LlmResult:
    text: str
    model: str
    slot: str
    usage: LlmUsage = field(default_factory=LlmUsage)
    parsed: Any = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]

    def declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.parameters,
        )


@dataclass
class AgentEvent:
    kind: str  # text | tool_call | tool_result | done | error
    text: str = ""
    tool: str = ""
    payload: Any = None


def _is_quota_exception(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code == 429:
        return True
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if status == 429:
        return True
    message = str(exc)
    return "429" in message or "RESOURCE_EXHAUSTED" in message.upper()


def _usage_from(response) -> LlmUsage:
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        return LlmUsage()
    return LlmUsage(
        prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
        total_tokens=int(getattr(meta, "total_token_count", 0) or 0),
    )


def extract_json(text: str) -> Any:
    """Parse JSON even when the model wraps it in prose or fences."""
    if not text:
        raise ValueError("empty response")
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S | re.I)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Find the outermost object or array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("response was not valid JSON")


class GeminiClient:
    def __init__(self) -> None:
        self._client: genai.Client | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle ----------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(settings.gemini_api_key)

    async def _get_client(self) -> genai.Client:
        if not self.available:
            raise LlmUnavailable("Gemini API key is not configured")
        async with self._lock:
            if self._client is None:
                self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aio.aclose()
            except Exception:  # pragma: no cover - best effort
                pass
            self._client = None

    # -- internals ----------------------------------------------------------
    def _model_for(self, slot: str) -> str:
        return settings.gemini_model_quality if slot == "quality" else settings.gemini_model_fast

    def _fallback_slots(self, slot: str) -> list[str]:
        chain = [slot]
        if slot == "quality":
            chain.append("fast")
        return chain

    async def _acquire(self, slot: str, identity: str | None, background: bool) -> str:
        """Reserve quota, falling back from quality to fast. Returns the slot used."""
        last: QuotaExceeded | None = None
        for candidate in self._fallback_slots(slot):
            try:
                await quota.acquire(
                    candidate, identity=identity, background=background,
                    model=self._model_for(candidate),
                )
                return candidate
            except QuotaExceeded as exc:
                last = exc
                if exc.reason == "user":
                    raise LlmQuotaError("user", exc.reset_at, candidate) from exc
                continue
        reason = last.reason if last else "daily"
        raise LlmQuotaError(reason, getattr(last, "reset_at", None), slot)

    def _base_config(
        self,
        *,
        system_instruction: str | None,
        temperature: float,
        max_output_tokens: int,
        tools: list[types.Tool] | None,
        response_schema: dict | None,
        thinking_budget: int | None,
    ) -> types.GenerateContentConfig:
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if system_instruction:
            config.system_instruction = system_instruction
        if tools:
            config.tools = tools
        if response_schema:
            config.response_mime_type = "application/json"
            config.response_json_schema = response_schema
        if thinking_budget is not None:
            try:
                config.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)
            except Exception:  # pragma: no cover - model without thinking support
                pass
        return config

    async def _generate_once(
        self, *, model: str, contents, config: types.GenerateContentConfig, timeout: float
    ):
        client = await self._get_client()
        return await asyncio.wait_for(
            client.aio.models.generate_content(model=model, contents=contents, config=config),
            timeout=timeout,
        )

    async def _stream_once(
        self, *, model: str, contents, config: types.GenerateContentConfig, timeout: float
    ):
        client = await self._get_client()
        stream = await asyncio.wait_for(
            client.aio.models.generate_content_stream(model=model, contents=contents, config=config),
            timeout=timeout,
        )
        return stream

    async def _record_usage(self, response, slot: str, model: str) -> LlmUsage:
        usage = _usage_from(response)
        try:
            quota.record_tokens(slot, usage.prompt_tokens, usage.output_tokens, model)
        except Exception:  # pragma: no cover - counters must never break a reply
            pass
        return usage

    # -- public: plain generation ------------------------------------------
    async def generate(
        self,
        *,
        contents,
        system_instruction: str | None = None,
        tools: list[types.Tool] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.4,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        slot: str = "fast",
        identity: str | None = None,
        background: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        thinking_budget: int | None = None,
    ) -> LlmResult:
        if not self.available:
            raise LlmUnavailable("Gemini API key is not configured")
        used_slot = await self._acquire(slot, identity, background)
        model = self._model_for(used_slot)
        config = self._base_config(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            response_schema=response_schema,
            thinking_budget=thinking_budget,
        )
        try:
            response = await self._generate_once(
                model=model, contents=contents, config=config, timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            raise LlmError("The AI request timed out") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if _is_quota_exception(exc):
                quota.record_429(used_slot)
                raise LlmQuotaError("rpm", None, used_slot) from exc
            raise LlmError("The AI provider returned an error") from exc

        usage = await self._record_usage(response, used_slot, model)
        text = response.text or ""
        parsed = None
        if response_schema is not None:
            try:
                parsed = extract_json(text)
            except ValueError:
                parsed = None
        return LlmResult(text=text, model=model, slot=used_slot, usage=usage, parsed=parsed)

    async def generate_structured(
        self,
        *,
        contents,
        schema: dict,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        slot: str = "fast",
        identity: str | None = None,
        background: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> LlmResult:
        """Structured JSON with exactly one repair retry."""
        result = await self.generate(
            contents=contents,
            system_instruction=system_instruction,
            response_schema=schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            slot=slot,
            identity=identity,
            background=background,
            timeout=timeout,
        )
        if result.parsed is not None:
            return result

        repair_contents = list(_as_content_list(contents))
        repair_contents.append(types.Content(role="model", parts=[types.Part(text=result.text or "")]))
        repair_contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Your previous reply was not valid JSON for the required schema. "
                            "Return ONLY a valid JSON object. Do not add commentary or markdown."
                        )
                    )
                ],
            )
        )
        repaired = await self.generate(
            contents=repair_contents,
            system_instruction=system_instruction,
            response_schema=schema,
            temperature=0.1,
            max_output_tokens=max_output_tokens,
            slot=slot,
            identity=identity,
            background=background,
            timeout=timeout,
        )
        if repaired.parsed is None:
            raise LlmError("The AI returned invalid structured data")
        return repaired

    # -- public: streaming --------------------------------------------------
    async def stream_text(
        self,
        *,
        contents,
        system_instruction: str | None = None,
        temperature: float = 0.5,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        slot: str = "fast",
        identity: str | None = None,
        background: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> AsyncIterator[str]:
        if not self.available:
            raise LlmUnavailable("Gemini API key is not configured")
        used_slot = await self._acquire(slot, identity, background)
        model = self._model_for(used_slot)
        config = self._base_config(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=None,
            response_schema=None,
            thinking_budget=None,
        )
        try:
            stream = await self._stream_once(
                model=model, contents=contents, config=config, timeout=timeout
            )
            async for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if _is_quota_exception(exc):
                quota.record_429(used_slot)
                raise LlmQuotaError("rpm", None, used_slot) from exc
            raise LlmError("The AI provider returned an error") from exc

    # -- public: manual tool loop ------------------------------------------
    async def run_tool_loop(
        self,
        *,
        contents,
        tools: list[ToolSpec],
        system_instruction: str | None = None,
        temperature: float = 0.4,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        slot: str = "fast",
        identity: str | None = None,
        max_steps: int = MAX_TOOL_STEPS,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> AsyncIterator[AgentEvent]:
        """Stream an answer while executing tools ourselves.

        Tool calls are declared with ``disable=True`` automatic calling, so the
        model can never invoke anything we did not register.
        """
        if not self.available:
            yield AgentEvent(kind="error", text="unavailable")
            return
        by_name = {tool.name: tool for tool in tools}
        declarations = [tool.declaration() for tool in tools]
        gemini_tools = [types.Tool(function_declarations=declarations)] if declarations else None
        history = _as_content_list(contents)

        for step in range(max(1, max_steps)):
            # The user's daily budget is charged once per conversation turn,
            # not once per internal tool step.
            used_slot = await self._acquire(slot, identity if step == 0 else None, False)
            model = self._model_for(used_slot)
            config = self._base_config(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                tools=gemini_tools,
                response_schema=None,
                thinking_budget=None,
            )
            text_parts: list[str] = []
            calls: list[types.FunctionCall] = []
            seen_calls: set[str] = set()
            try:
                stream = await self._stream_once(
                    model=model, contents=history, config=config, timeout=timeout
                )
                async for chunk in stream:
                    chunk_text = getattr(chunk, "text", None)
                    if chunk_text:
                        text_parts.append(chunk_text)
                        yield AgentEvent(kind="text", text=chunk_text)
                    for call in getattr(chunk, "function_calls", None) or []:
                        if not call or not call.name:
                            continue
                        signature = f"{call.name}:{json.dumps(call.args or {}, sort_keys=True, default=str)}"
                        if signature in seen_calls:
                            continue
                        seen_calls.add(signature)
                        calls.append(call)
            except asyncio.CancelledError:
                raise
            except LlmQuotaError:
                raise
            except Exception as exc:
                if _is_quota_exception(exc):
                    quota.record_429(used_slot)
                    raise LlmQuotaError("rpm", None, used_slot) from exc
                raise LlmError("The AI provider returned an error") from exc

            if not calls:
                yield AgentEvent(kind="done", text="".join(text_parts))
                return

            history.append(
                types.Content(
                    role="model",
                    parts=[types.Part(function_call=call) for call in calls],
                )
            )
            for call in calls:
                spec = by_name.get(call.name or "")
                yield AgentEvent(kind="tool_call", tool=call.name or "", payload=call.args or {})
                if spec is None:
                    result: Any = {"error": f"Unknown tool {call.name}"}
                else:
                    try:
                        result = await spec.handler(**(call.args or {}))
                    except Exception as exc:  # tool errors must not kill the chat
                        log.warning("Tool %s failed: %s", call.name, type(exc).__name__)
                        result = {"error": "The tool could not complete that request."}
                yield AgentEvent(kind="tool_result", tool=call.name or "", payload=result)
                history.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=call.name or "",
                                response={"result": _json_safe(result)},
                            )
                        ],
                    )
                )

        yield AgentEvent(kind="error", text="tool_limit")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


def _as_content_list(contents) -> list[types.Content]:
    if isinstance(contents, str):
        return [types.Content(role="user", parts=[types.Part(text=contents)])]
    if isinstance(contents, types.Content):
        return [contents]
    return [
        item if isinstance(item, types.Content) else types.Content(role="user", parts=[types.Part(text=str(item))])
        for item in contents
    ]


llm = GeminiClient()
