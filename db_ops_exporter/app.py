import os
import re
import threading
import time
from datetime import datetime, timezone

import mysql.connector
import oracledb
from prometheus_client import Gauge, start_http_server


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dataguard_lag_seconds(raw):
    if raw is None:
        return None

    text = str(raw).strip()
    if not text or text.upper() == "UNKNOWN":
        return None

    # Matches formats like "+00 00:00:05" or "0 00:01:30"
    match = re.match(r"^[+]?(-?\d+)\s+(\d{2}):(\d{2}):(\d{2})$", text)
    if not match:
        return None

    days, hours, minutes, seconds = [int(group) for group in match.groups()]
    total = (days * 24 * 3600) + (hours * 3600) + (minutes * 60) + seconds
    return float(max(total, 0))


class DbOpsCollector:
    def __init__(self):
        self.poll_interval_seconds = int(_env("DB_OPS_POLL_INTERVAL_SECONDS", "60"))

        self.environment = _env("DB_OPS_ENVIRONMENT", "pilot")
        self.team = _env("DB_OPS_TEAM", "dba")
        self.owner = _env("DB_OPS_OWNER", "dba-team")

        self.oracle_enabled = _env("DB_OPS_ENABLE_ORACLE", "true").lower() == "true"
        self.mysql_enabled = _env("DB_OPS_ENABLE_MYSQL", "true").lower() == "true"

        self.oracle_user = _env("ORACLE_MONITOR_USER", "monitor")
        self.oracle_password = _env("ORACLE_MONITOR_PASSWORD")
        self.oracle_dsn = _env("ORACLE_DSN", "oracle-db:1521/FREEPDB1")

        self.mysql_host = _env("MYSQL_HOST", "mysql-db")
        self.mysql_port = int(_env("MYSQL_PORT", "3306"))
        self.mysql_user = _env("MYSQL_MONITOR_USER", "monitor")
        self.mysql_password = _env("MYSQL_MONITOR_PASSWORD")

        self.backup_critical_seconds = int(_env("DB_BACKUP_CRITICAL_SECONDS", "86400"))

        labels = ["instance", "service", "db_engine", "environment", "team", "owner"]

        self.db_backup_last_success_timestamp_seconds = Gauge(
            "db_backup_last_success_timestamp_seconds",
            "Unix timestamp of latest successful backup.",
            labels,
        )
        self.db_backup_age_seconds = Gauge(
            "db_backup_age_seconds",
            "Age in seconds since latest successful backup.",
            labels,
        )
        self.db_backup_status = Gauge(
            "db_backup_status",
            "Backup health status: 1=ok, 0=stale/failed/unknown.",
            labels,
        )
        self.db_backup_collection_supported = Gauge(
            "db_backup_collection_supported",
            "Backup metric collection supported for this engine/instance: 1=yes, 0=no.",
            labels,
        )
        self.db_replication_configured = Gauge(
            "db_replication_configured",
            "Replication configured: 1=yes, 0=no.",
            labels,
        )
        self.db_replication_lag_seconds = Gauge(
            "db_replication_lag_seconds",
            "Replication lag in seconds when configured.",
            labels,
        )
        self.db_replication_io_thread_running = Gauge(
            "db_replication_io_thread_running",
            "MySQL replication IO thread running: 1=yes, 0=no.",
            labels,
        )
        self.db_replication_sql_thread_running = Gauge(
            "db_replication_sql_thread_running",
            "MySQL replication SQL thread running: 1=yes, 0=no.",
            labels,
        )
        self.db_dataguard_apply_lag_seconds = Gauge(
            "db_dataguard_apply_lag_seconds",
            "Oracle Data Guard apply lag in seconds when configured.",
            labels,
        )
        self.db_alertlog_error_count_15m = Gauge(
            "db_alertlog_error_count_15m",
            "DB alert/error log count in the last 15 minutes.",
            labels,
        )
        self.db_alertlog_critical_count_15m = Gauge(
            "db_alertlog_critical_count_15m",
            "DB critical alert/error count in the last 15 minutes.",
            labels,
        )
        self.db_alertlog_collection_supported = Gauge(
            "db_alertlog_collection_supported",
            "Alert-log metric collection supported for this engine/instance: 1=yes, 0=no.",
            labels,
        )
        self.db_ops_collection_success = Gauge(
            "db_ops_collection_success",
            "Exporter poll cycle success state per engine: 1=ok, 0=error.",
            labels,
        )
        self.db_ops_last_scrape_timestamp_seconds = Gauge(
            "db_ops_last_scrape_timestamp_seconds",
            "Unix timestamp of last collector poll per engine.",
            labels,
        )

    def _series_labels(self, instance: str, service: str, db_engine: str):
        return {
            "instance": instance,
            "service": service,
            "db_engine": db_engine,
            "environment": self.environment,
            "team": self.team,
            "owner": self.owner,
        }

    def _set_na(self, series):
        # Using 0 for unsupported/unconfigured keeps PromQL predictable.
        self.db_backup_last_success_timestamp_seconds.labels(**series).set(0)
        self.db_backup_age_seconds.labels(**series).set(0)
        self.db_backup_status.labels(**series).set(0)
        self.db_replication_lag_seconds.labels(**series).set(0)
        self.db_replication_io_thread_running.labels(**series).set(0)
        self.db_replication_sql_thread_running.labels(**series).set(0)
        self.db_dataguard_apply_lag_seconds.labels(**series).set(0)
        self.db_alertlog_error_count_15m.labels(**series).set(0)
        self.db_alertlog_critical_count_15m.labels(**series).set(0)

    def _collect_oracle(self):
        series = self._series_labels(self.oracle_dsn, "oracle", "oracle")
        self._set_na(series)

        if not self.oracle_enabled:
            self.db_backup_collection_supported.labels(**series).set(0)
            self.db_alertlog_collection_supported.labels(**series).set(0)
            self.db_replication_configured.labels(**series).set(0)
            self.db_ops_collection_success.labels(**series).set(1)
            self.db_ops_last_scrape_timestamp_seconds.labels(**series).set(time.time())
            return

        connection = None
        cursor = None
        success = 1

        try:
            connection = oracledb.connect(user=self.oracle_user, password=self.oracle_password, dsn=self.oracle_dsn)
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    SELECT
                      (SYSDATE - MAX(end_time)) * 86400 AS age_seconds,
                      (CAST(MAX(end_time) AS DATE) - DATE '1970-01-01') * 86400 AS last_success_ts
                    FROM v$rman_backup_job_details
                    WHERE status = 'COMPLETED'
                    """
                )
                backup_row = cursor.fetchone()
                backup_age = _safe_float(backup_row[0]) if backup_row else None
                backup_ts = _safe_float(backup_row[1]) if backup_row else None
                self.db_backup_collection_supported.labels(**series).set(1)
                if backup_age is None or backup_ts is None:
                    self.db_backup_status.labels(**series).set(0)
                else:
                    self.db_backup_age_seconds.labels(**series).set(max(backup_age, 0))
                    self.db_backup_last_success_timestamp_seconds.labels(**series).set(max(backup_ts, 0))
                    self.db_backup_status.labels(**series).set(1 if backup_age <= self.backup_critical_seconds else 0)
            except Exception as exc:
                print(f"[db_ops][oracle] backup collection unsupported: {exc}", flush=True)
                self.db_backup_collection_supported.labels(**series).set(0)
                self.db_backup_status.labels(**series).set(0)

            try:
                cursor.execute("SELECT value FROM v$dataguard_stats WHERE name = 'apply lag'")
                dg_row = cursor.fetchone()
                if not dg_row:
                    self.db_replication_configured.labels(**series).set(0)
                else:
                    lag_seconds = _parse_dataguard_lag_seconds(dg_row[0])
                    self.db_replication_configured.labels(**series).set(1)
                    self.db_replication_lag_seconds.labels(**series).set(lag_seconds if lag_seconds is not None else 0)
                    self.db_dataguard_apply_lag_seconds.labels(**series).set(lag_seconds if lag_seconds is not None else 0)
            except Exception as exc:
                print(f"[db_ops][oracle] replication metrics unavailable: {exc}", flush=True)
                self.db_replication_configured.labels(**series).set(0)

            try:
                cursor.execute(
                    """
                    SELECT
                      NVL(SUM(CASE WHEN message_type IN (2,3) THEN 1 ELSE 0 END), 0) AS error_count,
                      NVL(SUM(CASE WHEN message_level <= 2 THEN 1 ELSE 0 END), 0) AS critical_count
                    FROM v$diag_alert_ext
                    WHERE originating_timestamp > SYSTIMESTAMP - INTERVAL '15' MINUTE
                    """
                )
                alert_row = cursor.fetchone()
                error_count = _safe_float(alert_row[0]) if alert_row else 0
                critical_count = _safe_float(alert_row[1]) if alert_row else 0
                self.db_alertlog_collection_supported.labels(**series).set(1)
                self.db_alertlog_error_count_15m.labels(**series).set(error_count if error_count is not None else 0)
                self.db_alertlog_critical_count_15m.labels(**series).set(
                    critical_count if critical_count is not None else 0
                )
            except Exception as exc:
                print(f"[db_ops][oracle] alert-log metrics unavailable: {exc}", flush=True)
                self.db_alertlog_collection_supported.labels(**series).set(0)

        except Exception as exc:
            print(f"[db_ops][oracle] connection or base query failure: {exc}", flush=True)
            success = 0
            self.db_backup_collection_supported.labels(**series).set(0)
            self.db_alertlog_collection_supported.labels(**series).set(0)
            self.db_replication_configured.labels(**series).set(0)
        finally:
            self.db_ops_collection_success.labels(**series).set(success)
            self.db_ops_last_scrape_timestamp_seconds.labels(**series).set(time.time())
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def _collect_mysql(self):
        series = self._series_labels(f"{self.mysql_host}:{self.mysql_port}", "mysql", "mysql")
        self._set_na(series)

        if not self.mysql_enabled:
            self.db_backup_collection_supported.labels(**series).set(0)
            self.db_alertlog_collection_supported.labels(**series).set(0)
            self.db_replication_configured.labels(**series).set(0)
            self.db_ops_collection_success.labels(**series).set(1)
            self.db_ops_last_scrape_timestamp_seconds.labels(**series).set(time.time())
            return

        connection = None
        cursor = None
        success = 1

        try:
            connection = mysql.connector.connect(
                host=self.mysql_host,
                port=self.mysql_port,
                user=self.mysql_user,
                password=self.mysql_password,
                connection_timeout=5,
            )
            cursor = connection.cursor(dictionary=True)

            # Backup freshness from mysql.backup_history when available (e.g. enterprise backup metadata).
            try:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS table_count
                    FROM information_schema.tables
                    WHERE table_schema = 'mysql' AND table_name = 'backup_history'
                    """
                )
                table_row = cursor.fetchone()
                backup_supported = table_row and int(table_row.get("table_count", 0)) > 0
                if backup_supported:
                    cursor.execute(
                        """
                        SELECT
                          UNIX_TIMESTAMP(MAX(end_time)) AS last_success_ts,
                          TIMESTAMPDIFF(SECOND, MAX(end_time), NOW()) AS age_seconds
                        FROM mysql.backup_history
                        WHERE exit_state = 'SUCCESS'
                        """
                    )
                    backup_row = cursor.fetchone() or {}
                    backup_age = _safe_float(backup_row.get("age_seconds"))
                    backup_ts = _safe_float(backup_row.get("last_success_ts"))
                    self.db_backup_collection_supported.labels(**series).set(1)
                    if backup_age is None or backup_ts is None:
                        self.db_backup_status.labels(**series).set(0)
                    else:
                        self.db_backup_age_seconds.labels(**series).set(max(backup_age, 0))
                        self.db_backup_last_success_timestamp_seconds.labels(**series).set(max(backup_ts, 0))
                        self.db_backup_status.labels(**series).set(1 if backup_age <= self.backup_critical_seconds else 0)
                else:
                    self.db_backup_collection_supported.labels(**series).set(0)
                    self.db_backup_status.labels(**series).set(0)
            except Exception as exc:
                print(f"[db_ops][mysql] backup metrics unavailable: {exc}", flush=True)
                self.db_backup_collection_supported.labels(**series).set(0)
                self.db_backup_status.labels(**series).set(0)

            try:
                replica_row = None
                try:
                    cursor.execute("SHOW REPLICA STATUS")
                    replica_row = cursor.fetchone()
                except Exception:
                    cursor.execute("SHOW SLAVE STATUS")
                    replica_row = cursor.fetchone()

                if not replica_row:
                    self.db_replication_configured.labels(**series).set(0)
                else:
                    self.db_replication_configured.labels(**series).set(1)
                    lag = (
                        replica_row.get("Seconds_Behind_Source")
                        if "Seconds_Behind_Source" in replica_row
                        else replica_row.get("Seconds_Behind_Master")
                    )
                    io_running = replica_row.get("Replica_IO_Running") or replica_row.get("Slave_IO_Running")
                    sql_running = replica_row.get("Replica_SQL_Running") or replica_row.get("Slave_SQL_Running")
                    self.db_replication_lag_seconds.labels(**series).set(_safe_float(lag) or 0)
                    self.db_replication_io_thread_running.labels(**series).set(1 if str(io_running).upper() == "YES" else 0)
                    self.db_replication_sql_thread_running.labels(**series).set(1 if str(sql_running).upper() == "YES" else 0)
            except Exception as exc:
                print(f"[db_ops][mysql] replication metrics unavailable: {exc}", flush=True)
                self.db_replication_configured.labels(**series).set(0)

            # MySQL error log via performance_schema.error_log where available.
            try:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS table_count
                    FROM information_schema.tables
                    WHERE table_schema = 'performance_schema' AND table_name = 'error_log'
                    """
                )
                error_log_table = cursor.fetchone()
                if error_log_table and int(error_log_table.get("table_count", 0)) > 0:
                    cursor.execute(
                        """
                        SELECT
                          SUM(CASE WHEN UPPER(PRIO) IN ('ERROR','SYSTEM') THEN 1 ELSE 0 END) AS error_count,
                          SUM(CASE WHEN UPPER(PRIO) = 'ERROR' THEN 1 ELSE 0 END) AS critical_count
                        FROM performance_schema.error_log
                        WHERE logged > NOW() - INTERVAL 15 MINUTE
                        """
                    )
                    row = cursor.fetchone() or {}
                    self.db_alertlog_collection_supported.labels(**series).set(1)
                    self.db_alertlog_error_count_15m.labels(**series).set(_safe_float(row.get("error_count")) or 0)
                    self.db_alertlog_critical_count_15m.labels(**series).set(_safe_float(row.get("critical_count")) or 0)
                else:
                    self.db_alertlog_collection_supported.labels(**series).set(0)
            except Exception as exc:
                print(f"[db_ops][mysql] alert-log metrics unavailable: {exc}", flush=True)
                self.db_alertlog_collection_supported.labels(**series).set(0)

        except Exception as exc:
            print(f"[db_ops][mysql] connection or base query failure: {exc}", flush=True)
            success = 0
            self.db_backup_collection_supported.labels(**series).set(0)
            self.db_alertlog_collection_supported.labels(**series).set(0)
            self.db_replication_configured.labels(**series).set(0)
        finally:
            self.db_ops_collection_success.labels(**series).set(success)
            self.db_ops_last_scrape_timestamp_seconds.labels(**series).set(time.time())
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def run(self):
        while True:
            start = datetime.now(timezone.utc)
            self._collect_oracle()
            self._collect_mysql()
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            sleep_for = max(self.poll_interval_seconds - elapsed, 1)
            time.sleep(sleep_for)


if __name__ == "__main__":
    port = int(_env("DB_OPS_EXPORTER_PORT", "9187"))
    start_http_server(port)

    collector = DbOpsCollector()
    thread = threading.Thread(target=collector.run, daemon=True)
    thread.start()

    while True:
        time.sleep(3600)
