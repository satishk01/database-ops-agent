"""
AWS Lambda streaming handler for API Gateway REST API with ResponseTransferMode=STREAM.

Uses awslambda.streamifyResponse pattern to stream SSE chunks from the
FastAPI agent back through API Gateway without buffering.
"""

import json
import asyncio
import logging
from app.config import settings
from app.guardrails import detect_prompt_injection, apply_bedrock_guardrail, sanitize_pii
from app.agents.healthcheck_agent import create_healthcheck_agent
from app.agents.action_agent import create_action_agent
from app.agents.supervisor_agent import create_supervisor_agent

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AGENT_FACTORIES = {
    "healthcheck": create_healthcheck_agent,
    "action": create_action_agent,
    "supervisor": create_supervisor_agent,
}

# 8 null bytes delimiter required by API Gateway streaming protocol
NULL_DELIMITER = b"\x00" * 8


def handler(event, response_stream, context):
    """Lambda streaming handler — invoked via response-streaming-invocations."""

    # Parse the request
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        body = {}

    path = event.get("path", "")
    method = event.get("httpMethod", "GET")

    # ── Health check (non-streaming) ────────────────────────────────
    if path.endswith("/health"):
        _write_response(response_stream, 200, {"status": "ok"})
        return

    # ── OPTIONS (CORS preflight) ────────────────────────────────────
    if method == "OPTIONS":
        _write_response(response_stream, 200, {}, cors=True)
        return

    # ── POST /api/chat — streaming agent response ──────────────────
    message = body.get("message", "")
    agent_type = body.get("agent_type", "supervisor")

    if not message:
        _write_response(response_stream, 400, {"error": "message is required"})
        return

    # Guardrails check
    is_injection, reason = detect_prompt_injection(message)
    if is_injection:
        _write_sse_response(response_stream, agent_type, [
            {"event": "error", "data": f"Blocked: {reason}"},
        ])
        return

    checked_input, was_blocked = apply_bedrock_guardrail(message, "INPUT")
    if was_blocked:
        _write_sse_response(response_stream, agent_type, [
            {"event": "error", "data": checked_input},
        ])
        return

    # Run agent with streaming
    factory = AGENT_FACTORIES.get(agent_type)
    if not factory:
        _write_response(response_stream, 400, {"error": f"Unknown agent: {agent_type}"})
        return

    _stream_agent_response(response_stream, factory, checked_input, agent_type)


def _stream_agent_response(response_stream, factory, message, agent_type):
    """Run the agent and stream SSE events through the response stream."""

    # Write HTTP metadata (required by API Gateway streaming protocol)
    metadata = json.dumps({
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Accel-Buffering": "no",
        }
    })
    response_stream.write(metadata.encode("utf-8"))
    response_stream.write(NULL_DELIMITER)

    tools_used = []

    def streaming_handler(**kwargs):
        """Callback that writes SSE chunks as the agent thinks."""
        try:
            if "data" in kwargs:
                chunk = kwargs["data"]
                if chunk:
                    sse_line = f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                    response_stream.write(sse_line.encode("utf-8"))
            elif "current_tool_use" in kwargs:
                tool = kwargs["current_tool_use"]
                name = tool.get("name")
                if name and name not in tools_used:
                    tools_used.append(name)
                    sse_line = f"data: {json.dumps({'type': 'tool', 'tool': name})}\n\n"
                    response_stream.write(sse_line.encode("utf-8"))
        except Exception as e:
            logger.warning(f"Stream write error: {e}")

    try:
        agent = factory(callback_handler=streaming_handler)
        result = agent(message)

        # Final message with complete response and tools used
        response_text = str(result.message) if hasattr(result, "message") else str(result)
        safe_response = sanitize_pii(response_text)

        done_event = json.dumps({
            "type": "done",
            "agent_type": agent_type,
            "tools_used": tools_used,
            "final_response": safe_response,
        })
        response_stream.write(f"data: {done_event}\n\n".encode("utf-8"))

    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        err_event = json.dumps({"type": "error", "message": str(e)})
        response_stream.write(f"data: {err_event}\n\n".encode("utf-8"))

    response_stream.close()


def _write_response(response_stream, status_code, body, cors=False):
    """Write a non-streaming JSON response."""
    headers = {"Content-Type": "application/json"}
    if cors:
        headers.update({
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
            "Access-Control-Allow-Headers": "*",
        })

    metadata = json.dumps({"statusCode": status_code, "headers": headers})
    response_stream.write(metadata.encode("utf-8"))
    response_stream.write(NULL_DELIMITER)
    response_stream.write(json.dumps(body).encode("utf-8"))
    response_stream.close()


def _write_sse_response(response_stream, agent_type, events):
    """Write a short SSE response (for errors/blocks)."""
    metadata = json.dumps({
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
        }
    })
    response_stream.write(metadata.encode("utf-8"))
    response_stream.write(NULL_DELIMITER)
    for evt in events:
        sse_line = f"data: {json.dumps({'type': evt['event'], 'content': evt['data']})}\n\n"
        response_stream.write(sse_line.encode("utf-8"))
    done = json.dumps({"type": "done", "agent_type": agent_type, "tools_used": [], "final_response": ""})
    response_stream.write(f"data: {done}\n\n".encode("utf-8"))
    response_stream.close()


# Register as streaming handler
handler = handler  # noqa — the function name 'handler' is used by the CMD in Dockerfile
