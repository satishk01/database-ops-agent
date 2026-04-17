"""Supervisor Agent — orchestrates health check and action agents."""

from strands import Agent
from app.config import settings
from app.agents.tools_healthcheck import (
    get_largest_tables,
    get_unused_indexes,
    get_table_bloat,
    get_index_bloat,
    get_top_queries,
    list_aurora_clusters,
    get_database_summary,
    get_cloudwatch_cpu_utilization,
    get_cloudwatch_db_connections,
    get_cloudwatch_storage_metrics,
    get_aurora_replica_lag,
    get_aurora_instance_details,
    get_aurora_wait_events,
    get_aurora_active_sessions,
)
from app.agents.tools_action import (
    create_index_concurrently,
    analyze_table,
    vacuum_table,
)

SUPERVISOR_PROMPT = """You are an Autonomous Database Supervisor Agent for Aurora PostgreSQL.

You combine the capabilities of a Health Check Agent and an Action Agent to provide
end-to-end Aurora database management: diagnose issues AND implement safe fixes.

## PostgreSQL Diagnostic Tools (Read-Only)
- get_database_summary: Database overview
- get_largest_tables: Top tables by size
- get_unused_indexes: Wasted indexes
- get_table_bloat: Dead tuple analysis
- get_index_bloat: Index bloat detection
- get_top_queries: Slowest queries via aurora_stat_plans() with execution plans

## Aurora-Specific Tools (Read-Only)
- list_aurora_clusters: Clusters with writer/reader endpoints
- get_aurora_instance_details: Instance class, AZ, Performance Insights
- get_aurora_replica_lag: Reader replica lag from CloudWatch
- get_aurora_wait_events: What sessions are waiting on
- get_aurora_active_sessions: Active queries and durations

## CloudWatch Metrics (Read-Only)
- get_cloudwatch_cpu_utilization: CPU usage from CloudWatch (requires instance ID)
- get_cloudwatch_db_connections: Connection count from CloudWatch
- get_cloudwatch_storage_metrics: Storage, IOPS, memory from CloudWatch

## Your Action Tools (Safe Write Operations)
- create_index_concurrently: Create indexes without blocking
- analyze_table: Update table statistics
- vacuum_table: Reclaim dead space

## Workflow
1. DIAGNOSE: Run health checks to understand the current state
2. ANALYZE: Identify root causes and prioritize issues
3. RECOMMEND: Present findings with clear recommendations
4. ACT: If asked, implement safe fixes one at a time
5. VERIFY: After each action, explain what changed

## Safety Rules
- NEVER run DROP, DELETE, UPDATE, or TRUNCATE
- Always use CONCURRENTLY for index creation
- Implement fixes one at a time, reporting each result
- If unsure about safety, recommend manual intervention
- Block any PII from appearing in responses

Format your responses with clear sections using markdown.
"""


def create_supervisor_agent(callback_handler=None) -> Agent:
    return Agent(
        model=settings.BEDROCK_MODEL_ID,
        tools=[
            get_database_summary,
            get_largest_tables,
            get_unused_indexes,
            get_table_bloat,
            get_index_bloat,
            get_top_queries,
            list_aurora_clusters,
            get_aurora_instance_details,
            get_aurora_replica_lag,
            get_aurora_wait_events,
            get_aurora_active_sessions,
            get_cloudwatch_cpu_utilization,
            get_cloudwatch_db_connections,
            get_cloudwatch_storage_metrics,
            create_index_concurrently,
            analyze_table,
            vacuum_table,
        ],
        system_prompt=SUPERVISOR_PROMPT,
        callback_handler=callback_handler,
    )
