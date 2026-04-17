"""FastAPI backend for DataOps Agent."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.guardrails import detect_prompt_injection, apply_bedrock_guardrail, sanitize_pii
from app.agents.healthcheck_agent import create_healthcheck_agent
from app.agents.action_agent import create_action_agent
from app.agents.supervisor_agent import create_supervisor_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DataOps Agent backend starting...")
    yield
    logger.info("DataOps Agent backend shutting down.")


app = FastAPI(
    title="DataOps Agent API",
    description="AI-powered database operations agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    agent_type: str = "supervisor"  # "healthcheck", "action", or "supervisor"


class ChatResponse(BaseModel):
    response: str
    agent_type: str
    tools_used: list[str] = []


AGENT_FACTORIES = {
    "healthcheck": create_healthcheck_agent,
    "action": create_action_agent,
    "supervisor": create_supervisor_agent,
}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the selected agent and get a response."""
    # 1. Prompt injection detection
    is_injection, reason = detect_prompt_injection(request.message)
    if is_injection:
        return ChatResponse(
            response=f"⛔ Request blocked: {reason}",
            agent_type=request.agent_type,
            tools_used=[],
        )

    # 2. Apply Bedrock Guardrail on input
    checked_input, was_blocked = await asyncio.to_thread(
        apply_bedrock_guardrail, request.message, "INPUT"
    )
    if was_blocked:
        return ChatResponse(
            response=f"⛔ {checked_input}",
            agent_type=request.agent_type,
            tools_used=[],
        )

    factory = AGENT_FACTORIES.get(request.agent_type)
    if not factory:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {request.agent_type}")

    tools_used = []

    def tracking_handler(**kwargs):
        if "current_tool_use" in kwargs:
            tool = kwargs["current_tool_use"]
            name = tool.get("name")
            if name and name not in tools_used:
                tools_used.append(name)

    try:
        agent = factory(callback_handler=tracking_handler)
        result = await asyncio.to_thread(agent, checked_input)
        response_text = str(result.message) if hasattr(result, "message") else str(result)

        # 3. Apply Bedrock Guardrail on output + local PII sanitization
        safe_response, _ = await asyncio.to_thread(
            apply_bedrock_guardrail, response_text, "OUTPUT"
        )
        safe_response = sanitize_pii(safe_response)

        return ChatResponse(
            response=safe_response,
            agent_type=request.agent_type,
            tools_used=tools_used,
        )
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stream")
async def stream_chat(message: str, agent_type: str = "supervisor"):
    """Stream agent responses via Server-Sent Events."""
    factory = AGENT_FACTORIES.get(agent_type)
    if not factory:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {agent_type}")

    async def event_generator():
        queue = asyncio.Queue()

        def sse_handler(**kwargs):
            if "data" in kwargs:
                queue.put_nowait({"event": "text", "data": kwargs["data"]})
            elif "current_tool_use" in kwargs:
                tool = kwargs["current_tool_use"]
                name = tool.get("name")
                if name:
                    queue.put_nowait({"event": "tool", "data": json.dumps({"tool": name})})

        async def run_agent():
            try:
                agent = factory(callback_handler=sse_handler)
                await asyncio.to_thread(agent, message)
            except Exception as e:
                queue.put_nowait({"event": "error", "data": str(e)})
            finally:
                queue.put_nowait(None)  # sentinel

        asyncio.create_task(run_agent())

        while True:
            item = await queue.get()
            if item is None:
                yield {"event": "done", "data": ""}
                break
            yield item

    return EventSourceResponse(event_generator())


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "dataops-agent"}
