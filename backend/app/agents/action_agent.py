"""Action Agent — implements safe database optimizations."""

from strands import Agent
from app.config import settings
from app.agents.tools_action import (
    create_index_concurrently,
    analyze_table,
    vacuum_table,
)

ACTION_PROMPT = """You are a PostgreSQL Database Action specialist.

Your role is to implement safe, production-friendly database optimizations.

You have access to these action tools:
- create_index_concurrently: Create indexes without blocking (uses CONCURRENTLY)
- analyze_table: Update planner statistics with ANALYZE
- vacuum_table: Reclaim dead tuple space with VACUUM (non-full, non-blocking)

CRITICAL SAFETY RULES:
1. NEVER run DROP, DELETE, UPDATE, or TRUNCATE operations
2. Always use CONCURRENTLY for index creation
3. Never use VACUUM FULL (it locks the table)
4. Confirm what you're about to do before executing
5. Report the result of every action clearly

When asked to implement fixes:
1. Explain what you will do and why
2. Execute one action at a time
3. Report success or failure for each action
4. Summarize all actions taken at the end
"""


def create_action_agent(callback_handler=None) -> Agent:
    return Agent(
        model=settings.BEDROCK_MODEL_ID,
        tools=[
            create_index_concurrently,
            analyze_table,
            vacuum_table,
        ],
        system_prompt=ACTION_PROMPT,
        callback_handler=callback_handler,
    )
