from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any, cast
from urllib.parse import unquote


def _string_value(key: str, summary: str) -> str:
    normalized = key.replace("_", " ").replace("-", " ").strip() or "value"
    if key == "summary":
        return summary
    if key == "posture":
        return "fake provider posture"
    if key == "rationale":
        return "fake provider rationale"
    if key == "riskSummary":
        return "fake provider risk summary"
    if key == "implementationNotes":
        return "fake provider implementation notes"
    if len(key) > 80:
        return (f"fake provider wide output for {key} ") * 12
    return f"fake provider {normalized}"


def _schema_type(schema: dict[str, object]) -> str:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return next((str(item) for item in schema_type if item != "null"), "string")
    if isinstance(schema_type, str):
        return schema_type
    if isinstance(schema.get("properties"), dict):
        return "object"
    if isinstance(schema.get("items"), dict):
        return "array"
    return "string"


def _resolve_ref(root_schema: dict[str, object], ref: object) -> object | None:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    current: object = root_schema
    for part in ref[2:].split("/"):
        if not isinstance(current, dict):
            return None
        current = current.get(part.replace("~1", "/").replace("~0", "~"))
    return current


def _schema_value(
    key: str,
    schema: object,
    summary: str,
    root_schema: dict[str, object],
    depth: int = 0,
) -> object:
    if depth > 12 or not isinstance(schema, dict):
        return _string_value(key, summary)
    resolved = _resolve_ref(root_schema, schema.get("$ref"))
    if resolved is not None:
        return _schema_value(key, resolved, summary, root_schema, depth + 1)
    for combiner in ("allOf", "anyOf", "oneOf"):
        options = schema.get(combiner)
        if isinstance(options, list) and options:
            return _schema_value(key, options[0], summary, root_schema, depth + 1)
    if "const" in schema:
        return schema["const"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    schema_type = _schema_type(schema)
    if schema_type == "object":
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return {}
        return {
            str(property_key): _schema_value(
                str(property_key), property_schema, summary, root_schema, depth + 1
            )
            for property_key, property_schema in properties.items()
        }
    if schema_type == "array":
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and min_items > 0:
            return [_schema_value(key, schema.get("items", {}), summary, root_schema, depth + 1)]
        return []
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.23
    if schema_type == "boolean":
        return True
    return _string_value(key, summary)


def _schema_output(schema: object, summary: str) -> object:
    if not isinstance(schema, dict):
        return {"summary": summary}
    return _schema_value("summary", schema, summary, schema)


def _prompted_schema(payload: dict[str, Any]) -> object | None:
    messages = payload.get("messages", payload.get("input", []))
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        texts = (
            [content]
            if isinstance(content, str)
            else (
                [part.get("text") for part in content if isinstance(part, dict)]
                if isinstance(content, list)
                else []
            )
        )
        for text in texts:
            if not isinstance(text, str):
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get("outputContract"), dict):
                return value["outputContract"]
    return None


def _responses_schema(payload: dict[str, Any]) -> object | None:
    text = payload.get("text")
    if not isinstance(text, dict):
        return None
    text_format = text.get("format")
    if not isinstance(text_format, dict) or text_format.get("type") != "json_schema":
        return None
    return text_format.get("schema")


def _chat_schema(payload: dict[str, Any]) -> object | None:
    response_format = payload.get("response_format")
    if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
        return None
    json_schema = response_format.get("json_schema")
    if not isinstance(json_schema, dict):
        return None
    return json_schema.get("schema")


def _response(
    summary: str,
    *,
    include_usage: bool = True,
    schema: object | None = None,
    model: str = "fake-model",
) -> dict[str, Any]:
    output = _schema_output(schema, summary)
    output_text = json.dumps(output)
    body: dict[str, Any] = {
        "id": "fake-response",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": model,
        "output": [
            {
                "id": "fake-message",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": output_text, "annotations": []}],
            }
        ],
        "output_text": output_text,
    }
    if include_usage:
        body["usage"] = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
    return body


def _normalize_base_path(base_path: str) -> str:
    normalized = base_path.strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


class FakeOpenAIProviderServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.request_log: list[dict[str, Any]] = []
        self.held_models: dict[str, Event] = {}


@contextmanager
def run_fake_openai_provider(
    host: str = "127.0.0.1",
    *,
    base_path: str = "/v1",
    request_log: list[dict[str, Any]] | None = None,
) -> Iterator[str]:
    normalized_base_path = _normalize_base_path(base_path)
    server = FakeOpenAIProviderServer((host, 0), FakeOpenAIProviderHandler)
    server.request_log = request_log if request_log is not None else []
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{server.server_port}{normalized_base_path}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class FakeOpenAIProviderHandler(BaseHTTPRequestHandler):
    server_version = "SignalDeckFakeOpenAI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/control/state/"):
            model = unquote(self.path.removeprefix("/control/state/"))
            server = cast(FakeOpenAIProviderServer, self.server)
            entered = sum(item["payload"].get("model") == model for item in server.request_log)
            self._send_json(200, {"entered": entered})
            return
        self._send_json(404, {"error": {"message": "unsupported fake provider route"}})

    def do_POST(self) -> None:  # noqa: N802
        server = cast(FakeOpenAIProviderServer, self.server)
        if self.path.startswith("/control/hold/"):
            model = unquote(self.path.removeprefix("/control/hold/"))
            server.held_models[model] = Event()
            self._send_json(200, {"held": True})
            return
        if self.path.startswith("/control/release/"):
            model = unquote(self.path.removeprefix("/control/release/"))
            if model in server.held_models:
                server.held_models[model].set()
            self._send_json(200, {"released": True})
            return
        try:
            length = int(self.headers.get("content-length") or "0")
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "invalid json"}})
            return

        server = cast(FakeOpenAIProviderServer, self.server)
        server.request_log.append(
            {
                "method": "POST",
                "path": self.path,
                "payload": payload,
            }
        )

        held = server.held_models.get(str(payload.get("model")))
        if held is not None:
            held.wait(timeout=120)
        if self.path.endswith("/responses"):
            self._handle_responses(payload)
            return
        if self.path.endswith("/chat/completions"):
            self._handle_chat_completions(payload)
            return
        self._send_json(404, {"error": {"message": "unsupported fake provider route"}})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _handle_responses(self, payload: dict[str, Any]) -> None:
        model = str(payload.get("model") or "")
        schema = _responses_schema(payload) or _prompted_schema(payload)
        if "tools-disabled" in model and payload.get("tools"):
            self._send_json(400, {"error": {"message": "tool calls are unsupported"}})
            return
        if "reasoning-disabled" in model and "reasoning" in payload:
            self._send_json(400, {"error": {"message": "reasoning is unsupported"}})
            return
        if "json-object-only" in model:
            text_format = payload.get("text", {}).get("format", {})
            if text_format.get("type") == "json_schema":
                self._send_json(400, {"error": {"message": "json_schema is unsupported"}})
                return
            self._send_json(200, _response("fake json object fallback"))
            return
        if "missing-usage" in model:
            self._send_json(
                200,
                _response("fake missing usage", include_usage=False, schema=schema),
            )
            return
        self._send_json(200, _response("fake strict schema", schema=schema))

    def _handle_chat_completions(self, payload: dict[str, Any]) -> None:
        model = str(payload.get("model") or "")
        schema = _chat_schema(payload) or _prompted_schema(payload)
        if "tools-disabled" in model and payload.get("tools"):
            self._send_json(400, {"error": {"message": "tool calls are unsupported"}})
            return
        if "reasoning-disabled" in model and "reasoning_effort" in payload:
            self._send_json(400, {"error": {"message": "reasoning_effort is unsupported"}})
            return
        include_usage = "missing-usage" not in model
        summary = "fake chat output" if include_usage else "fake missing usage"
        body: dict[str, Any] = {
            "id": "fake-chat-completion",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(_schema_output(schema, summary)),
                    },
                }
            ],
        }
        # Opt-in E2E mode calls the advertised Oracle contract once before answering.
        if "oracle-tools" in model and not any(
            message.get("role") == "tool" for message in payload.get("messages", [])
        ):
            for entry in payload.get("tools", []):
                function = entry.get("function", {})
                properties = function.get("parameters", {}).get("properties", {})
                if "indicator" not in properties:
                    continue
                body["choices"][0].update(
                    finish_reason="tool_calls",
                    message={
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "controlled-oracle-sentiment",
                                "type": "function",
                                "function": {
                                    "name": function["name"],
                                    "arguments": json.dumps({"indicator": "fear_greed"}),
                                },
                            }
                        ],
                    },
                )
                break
        if include_usage:
            body["usage"] = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
        self._send_json(200, body)

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("x-request-id", "fake-openai-request")
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="18081")
    args = parser.parse_args()
    server = FakeOpenAIProviderServer((args.host, int(args.port)), FakeOpenAIProviderHandler)
    server.request_log = []
    server.serve_forever()


if __name__ == "__main__":
    main()
