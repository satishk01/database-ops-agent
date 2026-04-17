"""Health check tools for PostgreSQL database analysis."""

import json
import boto3
from strands import tool
from app.db import execute_query
from app.config import settings


@tool
def get_largest_tables() -> str:
    """Get the top 10 largest tables by disk usage in the database."""
    sql = """
    SELECT
        nspname AS schema,
        relname AS table_name,
        pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
        pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
        pg_size_pretty(pg_indexes_size(c.oid)) AS index_size,
        n_live_tup AS row_estimate
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
    WHERE c.relkind = 'r'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY pg_total_relation_size(c.oid) DESC
    LIMIT 10;
    """
    results = execute_query(sql)
    return json.dumps(results, default=str)


@tool
def get_unused_indexes() -> str:
    """Find indexes that have never been used by any query scan."""
    sql = """
    SELECT
        schemaname AS schema,
        relname AS table_name,
        indexrelname AS index_name,
        pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
        idx_scan AS times_used
    FROM pg_stat_user_indexes i
    JOIN pg_index idx ON i.indexrelid = idx.indexrelid
    WHERE idx_scan = 0
      AND NOT idx.indisunique
      AND NOT idx.indisprimary
    ORDER BY pg_relation_size(i.indexrelid) DESC
    LIMIT 20;
    """
    results = execute_query(sql)
    return json.dumps(results, default=str)


@tool
def get_table_bloat() -> str:
    """Detect tables with significant dead tuple bloat that may need VACUUM."""
    sql = """
    SELECT
        schemaname AS schema,
        relname AS table_name,
        n_live_tup AS live_tuples,
        n_dead_tup AS dead_tuples,
        CASE WHEN n_live_tup > 0
            THEN round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
            ELSE 0
        END AS bloat_pct,
        last_vacuum,
        last_autovacuum,
        last_analyze
    FROM pg_stat_user_tables
    WHERE n_dead_tup > 100
    ORDER BY n_dead_tup DESC
    LIMIT 15;
    """
    results = execute_query(sql)
    return json.dumps(results, default=str)


@tool
def get_index_bloat() -> str:
    """Find bloated indexes that are consuming more space than necessary."""
    sql = """
    SELECT
        schemaname AS schema,
        tablename AS table_name,
        indexname AS index_name,
        pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size,
        idx_scan AS scans,
        idx_tup_read AS tuples_read,
        idx_tup_fetch AS tuples_fetched
    FROM pg_stat_user_indexes
    JOIN pg_indexes ON pg_stat_user_indexes.indexrelname = pg_indexes.indexname
        AND pg_stat_user_indexes.schemaname = pg_indexes.schemaname
    ORDER BY pg_relation_size(indexname::regclass) DESC
    LIMIT 15;
    """
    results = execute_query(sql)
    return json.dumps(results, default=str)


@tool
def get_top_queries() -> str:
    """Get the top 10 most time-consuming queries with execution plans using Aurora's aurora_stat_plans()."""
    # Try Aurora-native aurora_stat_plans() first, fall back to pg_stat_statements
    aurora_sql = """
    SELECT
        userid::regrole AS db_user,
        queryid,
        datname AS db_name,
        substring(query, 1, 200) AS short_query,
        round((total_plan_time + total_exec_time)::numeric, 2) AS total_time_ms,
        calls,
        explain_plan
    FROM aurora_stat_plans(true) p, pg_database d
    WHERE p.dbid = d.oid
    ORDER BY total_time_ms DESC
    LIMIT 10;
    """
    fallback_sql = """
    SELECT
        queryid,
        substring(query, 1, 200) AS short_query,
        calls,
        round(total_exec_time::numeric, 2) AS total_exec_time_ms,
        round(mean_exec_time::numeric, 2) AS mean_exec_time_ms,
        rows
    FROM pg_stat_statements
    WHERE query NOT LIKE '%pg_stat_statements%'
      AND query NOT LIKE '%aurora_stat_plans%'
    ORDER BY total_exec_time DESC
    LIMIT 10;
    """
    try:
        results = execute_query(aurora_sql)
        return json.dumps({"source": "aurora_stat_plans", "queries": results}, default=str)
    except Exception:
        try:
            results = execute_query(fallback_sql)
            return json.dumps({"source": "pg_stat_statements", "queries": results}, default=str)
        except Exception as e:
            return json.dumps({"error": str(e), "hint": "Neither aurora_stat_plans() nor pg_stat_statements available"})


@tool
def list_aurora_clusters() -> str:
    """List all Aurora PostgreSQL clusters in the current AWS region with instance details."""
    try:
        rds = boto3.client("rds", region_name=settings.AWS_REGION)
        response = rds.describe_db_clusters()
        clusters = []
        for c in response.get("DBClusters", []):
            members = []
            for m in c.get("DBClusterMembers", []):
                members.append({
                    "instance_id": m["DBInstanceIdentifier"],
                    "is_writer": m["IsClusterWriter"],
                })
            clusters.append({
                "cluster_id": c["DBClusterIdentifier"],
                "engine": c["Engine"],
                "engine_version": c["EngineVersion"],
                "status": c["Status"],
                "writer_endpoint": c.get("Endpoint", "N/A"),
                "reader_endpoint": c.get("ReaderEndpoint", "N/A"),
                "port": c.get("Port", 5432),
                "multi_az": c.get("MultiAZ", False),
                "storage_encrypted": c.get("StorageEncrypted", False),
                "deletion_protection": c.get("DeletionProtection", False),
                "members": members,
            })
        return json.dumps(clusters, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_database_summary() -> str:
    """Get a high-level summary of the database: size, connections, uptime."""
    sql = """
    SELECT
        current_database() AS database_name,
        pg_size_pretty(pg_database_size(current_database())) AS database_size,
        (SELECT count(*) FROM pg_stat_activity) AS active_connections,
        (SELECT setting FROM pg_settings WHERE name = 'max_connections') AS max_connections,
        version() AS pg_version;
    """
    results = execute_query(sql)
    return json.dumps(results, default=str)


@tool
def get_cloudwatch_cpu_utilization(db_instance_id: str, period_minutes: int = 60) -> str:
    """
    Get CPU utilization metrics from CloudWatch for an RDS/Aurora instance.

    Args:
        db_instance_id: The RDS DB instance identifier.
        period_minutes: How far back to look in minutes (default 60).
    """
    from datetime import datetime, timedelta

    try:
        cw = boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=period_minutes)

        response = cw.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5-minute intervals
            Statistics=["Average", "Maximum"],
        )
        datapoints = sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"])
        results = []
        for dp in datapoints:
            results.append({
                "timestamp": dp["Timestamp"].isoformat(),
                "avg_cpu_pct": round(dp["Average"], 2),
                "max_cpu_pct": round(dp["Maximum"], 2),
            })

        summary = {}
        if results:
            avgs = [r["avg_cpu_pct"] for r in results]
            summary = {
                "instance": db_instance_id,
                "period_minutes": period_minutes,
                "current_avg_cpu": results[-1]["avg_cpu_pct"],
                "current_max_cpu": results[-1]["max_cpu_pct"],
                "period_avg_cpu": round(sum(avgs) / len(avgs), 2),
                "period_max_cpu": max(r["max_cpu_pct"] for r in results),
                "datapoints": results,
            }
        else:
            summary = {"instance": db_instance_id, "error": "No datapoints found. Check instance ID."}

        return json.dumps(summary, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_cloudwatch_db_connections(db_instance_id: str, period_minutes: int = 60) -> str:
    """
    Get database connection count metrics from CloudWatch for an RDS/Aurora instance.

    Args:
        db_instance_id: The RDS DB instance identifier.
        period_minutes: How far back to look in minutes (default 60).
    """
    from datetime import datetime, timedelta

    try:
        cw = boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=period_minutes)

        response = cw.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="DatabaseConnections",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=["Average", "Maximum"],
        )
        datapoints = sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"])
        results = [
            {
                "timestamp": dp["Timestamp"].isoformat(),
                "avg_connections": round(dp["Average"], 1),
                "max_connections": round(dp["Maximum"], 1),
            }
            for dp in datapoints
        ]
        return json.dumps({"instance": db_instance_id, "datapoints": results}, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_cloudwatch_storage_metrics(db_instance_id: str) -> str:
    """
    Get free storage space and read/write IOPS from CloudWatch for an RDS/Aurora instance.

    Args:
        db_instance_id: The RDS DB instance identifier.
    """
    from datetime import datetime, timedelta

    try:
        cw = boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=30)

        metrics = {}
        for metric_name in ["FreeStorageSpace", "ReadIOPS", "WriteIOPS", "FreeableMemory"]:
            response = cw.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric_name,
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=["Average"],
            )
            dps = response.get("Datapoints", [])
            if dps:
                latest = sorted(dps, key=lambda x: x["Timestamp"])[-1]
                val = latest["Average"]
                if metric_name in ("FreeStorageSpace", "FreeableMemory"):
                    val = round(val / (1024 ** 3), 2)  # bytes to GB
                    metrics[metric_name] = f"{val} GB"
                else:
                    metrics[metric_name] = round(val, 1)
            else:
                metrics[metric_name] = "N/A"

        return json.dumps({"instance": db_instance_id, **metrics}, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_aurora_replica_lag(db_instance_id: str, period_minutes: int = 60) -> str:
    """
    Get Aurora replica lag metrics from CloudWatch. High lag means readers are behind the writer.

    Args:
        db_instance_id: The Aurora reader instance identifier.
        period_minutes: How far back to look in minutes (default 60).
    """
    from datetime import datetime, timedelta

    try:
        cw = boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=period_minutes)

        response = cw.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="AuroraReplicaLag",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=["Average", "Maximum"],
        )
        datapoints = sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"])
        results = [
            {
                "timestamp": dp["Timestamp"].isoformat(),
                "avg_lag_ms": round(dp["Average"], 2),
                "max_lag_ms": round(dp["Maximum"], 2),
            }
            for dp in datapoints
        ]
        return json.dumps({"instance": db_instance_id, "metric": "AuroraReplicaLag", "datapoints": results}, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_aurora_instance_details() -> str:
    """Get detailed information about Aurora instances: class, AZ, role, engine version, and performance insights status."""
    try:
        cluster_id = settings.AURORA_CLUSTER_ID
        rds = boto3.client("rds", region_name=settings.AWS_REGION)

        if cluster_id:
            cluster_resp = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
            cluster = cluster_resp["DBClusters"][0]
            member_ids = [m["DBInstanceIdentifier"] for m in cluster.get("DBClusterMembers", [])]
        else:
            # Discover all Aurora instances
            resp = rds.describe_db_instances()
            member_ids = [
                i["DBInstanceIdentifier"]
                for i in resp["DBInstances"]
                if i.get("Engine", "").startswith("aurora")
            ]

        instances = []
        for iid in member_ids:
            inst_resp = rds.describe_db_instances(DBInstanceIdentifier=iid)
            inst = inst_resp["DBInstances"][0]
            instances.append({
                "instance_id": inst["DBInstanceIdentifier"],
                "instance_class": inst["DBInstanceClass"],
                "engine_version": inst["EngineVersion"],
                "availability_zone": inst.get("AvailabilityZone", "N/A"),
                "status": inst["DBInstanceStatus"],
                "is_writer": inst.get("DBClusterIdentifier", "") == cluster_id,
                "performance_insights": inst.get("PerformanceInsightsEnabled", False),
                "enhanced_monitoring": inst.get("MonitoringInterval", 0) > 0,
                "auto_minor_upgrade": inst.get("AutoMinorVersionUpgrade", False),
                "ca_certificate": inst.get("CACertificateIdentifier", "N/A"),
            })
        return json.dumps(instances, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_aurora_wait_events() -> str:
    """Get current wait events from Aurora PostgreSQL to identify what queries are waiting on."""
    sql = """
    SELECT
        wait_event_type,
        wait_event,
        state,
        count(*) AS session_count,
        array_agg(DISTINCT substring(query, 1, 80)) AS sample_queries
    FROM pg_stat_activity
    WHERE state != 'idle'
      AND pid != pg_backend_pid()
      AND wait_event IS NOT NULL
    GROUP BY wait_event_type, wait_event, state
    ORDER BY session_count DESC
    LIMIT 20;
    """
    try:
        results = execute_query(sql)
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_aurora_active_sessions() -> str:
    """Get currently active (non-idle) sessions with their queries, duration, and wait info."""
    sql = """
    SELECT
        pid,
        usename AS username,
        datname AS database,
        client_addr,
        state,
        wait_event_type,
        wait_event,
        substring(query, 1, 150) AS current_query,
        now() - query_start AS query_duration,
        now() - backend_start AS session_duration
    FROM pg_stat_activity
    WHERE state != 'idle'
      AND pid != pg_backend_pid()
    ORDER BY query_start ASC
    LIMIT 25;
    """
    try:
        results = execute_query(sql)
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
