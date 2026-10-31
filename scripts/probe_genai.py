import inspect

from google import genai
from google.genai import types

print("genai", getattr(genai, "__version__", "?"))

# Client() without a key is fine for introspection.
try:
    client = genai.Client(api_key="test")
except Exception as exc:  # pragma: no cover
    print("client error", exc)
    raise SystemExit(1)

print("aio type", type(client.aio))
print("aio.models", type(client.aio.models))
for name in ("generate_content", "generate_content_stream", "count_tokens"):
    fn = getattr(client.aio.models, name, None)
    print(name, "OK" if fn else "MISSING", inspect.signature(fn) if fn else "")

print("Part.from_function_response:", hasattr(types.Part, "from_function_response"))
print("Part.from_function_call:", hasattr(types.Part, "from_function_call"))
print("types.Tool fields:", list(getattr(types.Tool, "model_fields", {}).keys()))
print("FunctionDeclaration fields:", list(getattr(types.FunctionDeclaration, "model_fields", {}).keys()))
print("AFC fields:", list(getattr(types.AutomaticFunctionCallingConfig, "model_fields", {}).keys()))
print(
    "GenerateContentConfig sample:",
    [k for k in getattr(types.GenerateContentConfig, "model_fields", {}).keys()
     if k in ("system_instruction", "tools", "automatic_function_calling", "response_mime_type",
              "response_schema", "thinking_config", "max_output_tokens", "temperature",
              "safety_settings", "candidate_count")],
)
print("Content fields:", list(getattr(types.Content, "model_fields", {}).keys()))
print("GenerateContentResponse fields:", list(getattr(types.GenerateContentResponse, "model_fields", {}).keys()))
print("UsageMetadata fields:", list(getattr(types.GenerateContentResponseUsageMetadata, "model_fields", {}).keys()))
