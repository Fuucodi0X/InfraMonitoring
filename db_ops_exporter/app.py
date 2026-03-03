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
        self.db_user_collection_supported = Gauge(
            "db_user_collection_supported",
            "User-account metric collection supported for this engine/instance: 1=yes, 0=no.",
            labels,
        )
        self.db_tablespace_collection_supported = Gauge(
            "db_tablespace_collection_supported",
            "Tablespace metric collection supported for this engine/instance: 1=yes, 0=no.",
            labels,
        )
        self.db_user_accounts_total = Gauge(
            "db_user_accounts_total",
            "User account totals by state.",
            labels + ["state"],
        )
        self.db_user_password_expiry_days = Gauge(
            "db_user_password_expiry_days",
            "Days until user password expiry by account.",
            labels + ["username", "account_status"],
        )
        self.db_tablespace_used_percent = Gauge(
            "db_tablespace_used_percent",
            "Tablespace usage percentage.",
            labels + ["tablespace_name", "tablespace_type"],
        )
        self.db_tablespace_free_bytes = Gauge(
            "db_tablespace_free_bytes",
            "Free bytes for tablespace.",
            labels + ["tablespace_name", "tablespace_type"],
        )

        self._mysql_user_series_seen = set()
        self._mysql_tablespace_series_seen = set()

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
        self.db_user_collection_supported.labels(**series).set(0)
        self.db_tablespace_collection_supported.labels(**series).set(0)
        for state in ("open", "locked", "expired", "expiring_7d", "expiring_30d"):
            self.db_user_accounts_total.labels(**series, state=state).set(0)

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

            try:
                cursor.execute(
                    """
                    SELECT
                      COUNT(*) AS total_users,
                      SUM(CASE WHEN account_locked = 'Y' THEN 1 ELSE 0 END) AS locked_users,
                      SUM(CASE WHEN password_expired = 'Y' THEN 1 ELSE 0 END) AS expired_users,
                      SUM(
                        CASE
                          WHEN account_locked = 'Y' OR password_expired = 'Y' THEN 0
                          WHEN (
                            CASE
                              WHEN password_lifetime IS NOT NULL AND password_last_changed IS NOT NULL THEN
                                GREATEST(0, password_lifetime - DATEDIFF(CURDATE(), password_last_changed))
                              WHEN password_lifetime IS NULL
                                   AND @@default_password_lifetime > 0
                                   AND password_last_changed IS NOT NULL THEN
                                GREATEST(0, @@default_password_lifetime - DATEDIFF(CURDATE(), password_last_changed))
                              ELSE 99999
                            END
                          ) <= 7 THEN 1
                          ELSE 0
                        END
                      ) AS expiring_7d_users,
                      SUM(
                        CASE
                          WHEN account_locked = 'Y' OR password_expired = 'Y' THEN 0
                          WHEN (
                            CASE
                              WHEN password_lifetime IS NOT NULL AND password_last_changed IS NOT NULL THEN
                                GREATEST(0, password_lifetime - DATEDIFF(CURDATE(), password_last_changed))
                              WHEN password_lifetime IS NULL
                                   AND @@default_password_lifetime > 0
                                   AND password_last_changed IS NOT NULL THEN
                                GREATEST(0, @@default_password_lifetime - DATEDIFF(CURDATE(), password_last_changed))
                              ELSE 99999
                            END
                          ) <= 30 THEN 1
                          ELSE 0
                        END
                      ) AS expiring_30d_users
                    FROM mysql.user
                    WHERE User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema', 'root')
                    """
                )
                summary_row = cursor.fetchone() or {}
                total_users = int(summary_row.get("total_users") or 0)
                locked_users = int(summary_row.get("locked_users") or 0)
                expired_users = int(summary_row.get("expired_users") or 0)
                expiring_7d = int(summary_row.get("expiring_7d_users") or 0)
                expiring_30d = int(summary_row.get("expiring_30d_users") or 0)
                open_users = max(total_users - locked_users - expired_users, 0)

                self.db_user_collection_supported.labels(**series).set(1)
                self.db_user_accounts_total.labels(**series, state="open").set(open_users)
                self.db_user_accounts_total.labels(**series, state="locked").set(locked_users)
                self.db_user_accounts_total.labels(**series, state="expired").set(expired_users)
                self.db_user_accounts_total.labels(**series, state="expiring_7d").set(expiring_7d)
                self.db_user_accounts_total.labels(**series, state="expiring_30d").set(expiring_30d)

                cursor.execute(
                    """
                    SELECT
                      CONCAT(User, '@', Host) AS username,
                      CASE
                        WHEN account_locked = 'Y' THEN 'LOCKED'
                        WHEN password_expired = 'Y' THEN 'EXPIRED'
                        ELSE 'OPEN'
                      END AS account_status,
                      CASE
                        WHEN password_expired = 'Y' THEN 0
                        WHEN password_lifetime IS NOT NULL AND password_last_changed IS NOT NULL THEN
                          GREATEST(0, password_lifetime - DATEDIFF(CURDATE(), password_last_changed))
                        WHEN password_lifetime IS NULL
                             AND @@default_password_lifetime > 0
                             AND password_last_changed IS NOT NULL THEN
                          GREATEST(0, @@default_password_lifetime - DATEDIFF(CURDATE(), password_last_changed))
                        ELSE 99999
                      END AS days_until_expiry
                    FROM mysql.user
                    WHERE User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema', 'root')
                    """
                )
                active_user_series = set()
                for row in cursor.fetchall() or []:
                    username = str(row.get("username") or "")
                    account_status = str(row.get("account_status") or "UNKNOWN").upper()
                    days_until_expiry = _safe_float(row.get("days_until_expiry"))
                    if not username:
                        continue
                    self.db_user_password_expiry_days.labels(
                        **series,
                        username=username,
                        account_status=account_status,
                    ).set(days_until_expiry if days_until_expiry is not None else 99999)
                    active_user_series.add((username, account_status))

                stale_user_series = self._mysql_user_series_seen - active_user_series
                for username, account_status in stale_user_series:
                    try:
                        self.db_user_password_expiry_days.remove(
                            series["instance"],
                            series["service"],
                            series["db_engine"],
                            series["environment"],
                            series["team"],
                            series["owner"],
                            username,
                            account_status,
                        )
                    except KeyError:
                        pass
                self._mysql_user_series_seen = active_user_series
            except Exception as exc:
                print(f"[db_ops][mysql] user/account metrics unavailable: {exc}", flush=True)
                self.db_user_collection_supported.labels(**series).set(0)
                self.db_user_accounts_total.labels(**series, state="open").set(0)
                self.db_user_accounts_total.labels(**series, state="locked").set(0)
                self.db_user_accounts_total.labels(**series, state="expired").set(0)
                self.db_user_accounts_total.labels(**series, state="expiring_7d").set(0)
                self.db_user_accounts_total.labels(**series, state="expiring_30d").set(0)
                for username, account_status in self._mysql_user_series_seen:
                    try:
                        self.db_user_password_expiry_days.remove(
                            series["instance"],
                            series["service"],
                            series["db_engine"],
                            series["environment"],
                            series["team"],
                            series["owner"],
                            username,
                            account_status,
                        )
                    except KeyError:
                        pass
                self._mysql_user_series_seen = set()

            try:
                cursor.execute(
                    """
                    SELECT
                      table_schema AS tablespace_name,
                      'schema' AS tablespace_type,
                      COALESCE(SUM(data_length + index_length), 0) AS used_bytes,
                      COALESCE(SUM(data_free), 0) AS free_bytes,
                      CASE
                        WHEN COALESCE(SUM(data_length + index_length + data_free), 0) = 0 THEN 0
                        ELSE
                          (COALESCE(SUM(data_length + index_length), 0) /
                           COALESCE(SUM(data_length + index_length + data_free), 1)) * 100
                      END AS used_percent
                    FROM information_schema.tables
                    WHERE table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                    GROUP BY table_schema
                    """
                )
                rows = cursor.fetchall() or []
                self.db_tablespace_collection_supported.labels(**series).set(1)

                active_tablespace_series = set()
                for row in rows:
                    tablespace_name = str(row.get("tablespace_name") or "")
                    tablespace_type = str(row.get("tablespace_type") or "schema")
                    used_percent = _safe_float(row.get("used_percent")) or 0
                    free_bytes = _safe_float(row.get("free_bytes")) or 0
                    if not tablespace_name:
                        continue
                    self.db_tablespace_used_percent.labels(
                        **series,
                        tablespace_name=tablespace_name,
                        tablespace_type=tablespace_type,
                    ).set(max(used_percent, 0))
                    self.db_tablespace_free_bytes.labels(
                        **series,
                        tablespace_name=tablespace_name,
                        tablespace_type=tablespace_type,
                    ).set(max(free_bytes, 0))
                    active_tablespace_series.add((tablespace_name, tablespace_type))

                stale_tablespace_series = self._mysql_tablespace_series_seen - active_tablespace_series
                for tablespace_name, tablespace_type in stale_tablespace_series:
                    try:
                        self.db_tablespace_used_percent.remove(
                            series["instance"],
                            series["service"],
                            series["db_engine"],
                            series["environment"],
                            series["team"],
                            series["owner"],
                            tablespace_name,
                            tablespace_type,
                        )
                    except KeyError:
                        pass
                    try:
                        self.db_tablespace_free_bytes.remove(
                            series["instance"],
                            series["service"],
                            series["db_engine"],
                            series["environment"],
                            series["team"],
                            series["owner"],
                            tablespace_name,
                            tablespace_type,
                        )
                    except KeyError:
                        pass
                self._mysql_tablespace_series_seen = active_tablespace_series
            except Exception as exc:
                print(f"[db_ops][mysql] tablespace metrics unavailable: {exc}", flush=True)
                self.db_tablespace_collection_supported.labels(**series).set(0)
                for tablespace_name, tablespace_type in self._mysql_tablespace_series_seen:
                    try:
                        self.db_tablespace_used_percent.remove(
                            series["instance"],
                            series["service"],
                            series["db_engine"],
                            series["environment"],
                            series["team"],
                            series["owner"],
                            tablespace_name,
                            tablespace_type,
                        )
                    except KeyError:
                        pass
                    try:
                        self.db_tablespace_free_bytes.remove(
                            series["instance"],
                            series["service"],
                            series["db_engine"],
                            series["environment"],
                            series["team"],
                            series["owner"],
                            tablespace_name,
                            tablespace_type,
                        )
                    except KeyError:
                        pass
                self._mysql_tablespace_series_seen = set()

        except Exception as exc:
            print(f"[db_ops][mysql] connection or base query failure: {exc}", flush=True)
            success = 0
            self.db_backup_collection_supported.labels(**series).set(0)
            self.db_alertlog_collection_supported.labels(**series).set(0)
            self.db_replication_configured.labels(**series).set(0)
            self.db_user_collection_supported.labels(**series).set(0)
            self.db_tablespace_collection_supported.labels(**series).set(0)
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
