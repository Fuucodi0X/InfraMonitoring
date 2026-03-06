# DBA Monitoring Demo Guide

This guide demonstrates the current PoC: centralized Oracle/MySQL monitoring with low-noise routing, inhibition, and actionable alerts.

## Pre-Demo Setup

### 1. Configure and Start
```bash
cp .env.example .env
docker compose up -d
```

Wait 2-3 minutes, then verify:
```bash
docker compose ps
```

### 2. Open Tabs
- Prometheus: http://localhost:9091
- Alertmanager: http://localhost:9093
- Grafana: http://localhost:3000
- Mailpit: http://localhost:8025
- Webhook sink: http://localhost:8080

Recommended Grafana dashboard for this flow:
- `DBA Operations Comprehensive` (`/d/dba-ops-comprehensive/dba-operations-comprehensive`)

### 3. Validate Config
```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker exec prometheus sh -c 'promtool check rules /etc/prometheus/rules/*.yml'
docker exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

## Demo Flow

### Part 1: Baseline Health (2 minutes)
Show Prometheus targets page (`/targets`) and confirm these jobs are `UP`:
- `oracle_db`, `mysql_db`
- `node_oracle`, `node_mysql`
- `listener_oracle`, `listener_mysql`

Then show Alertmanager has no active alerts.

### Part 1.5: Seed Dashboard Activity Data (2-3 minutes)
Run:
```bash
./simulate-dashboard-activity.sh 10
```

Expected:
- User-expiry and account-health panels become populated (MySQL + Oracle where available).
- Backup freshness/status panels show non-zero values from seeded backup history.
- Tablespace usage panels populate for MySQL and Oracle.
- Activity trend charts show live movement during simulation runtime.

### Part 1.6: MySQL Password Expiry Alert Scenario (3 minutes)
The seed script already creates demo accounts for this scenario:
- `demo_expired` -> should trigger `MySQLUserPasswordExpired`
- `demo_expiring_soon` (5 days) -> should trigger `MySQLUserPasswordExpiryRisk`

Verify metrics immediately:
```bash
curl -s http://localhost:9091/api/v1/query --data-urlencode 'query=db_user_password_expiry_days{db_engine="mysql"}' | jq '.data.result[] | {user: .metric.username, status: .metric.account_status, days: .value[1]}'
```

Watch only password-expiry alerts:
```bash
curl -s http://localhost:9091/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname|test("MySQLUserPassword")) | {name:.labels.alertname, state:.state, user:.labels.username, severity:.labels.severity}'
```

Demo timing note:
- `MySQLUserPasswordExpired` has `for: 15m`
- `MySQLUserPasswordExpiryRisk` has `for: 30m`

For live demos, run the seed step at least 30 minutes before speaking, or temporarily lower `for` values for demo-only speed.

### Part 2: Availability Alert (3 minutes)
Trigger DB-down by stopping MySQL exporter:
```bash
docker compose stop mysqld_exporter
```

Expected:
- `MySQLDatabaseDown` fires after ~1 minute.
- Alert appears in Alertmanager as `critical`, `category=availability`.
- Notification goes to `pager-webhook` and critical email receiver.

Restore:
```bash
docker compose start mysqld_exporter
```

### Part 3: Listener Monitoring (3 minutes)
Trigger listener failure simulation by stopping Oracle DB container:
```bash
docker compose stop oracle
```

Expected:
- `OracleListenerDown` fires from blackbox probe (`probe_success == 0`).
- `OracleDatabaseDown` may also fire from exporter unreachability.
- Use this to explain symptom/operational alerting.

Restore:
```bash
docker compose start oracle
```

### Part 4: Capacity/Performance Warning Path (5 minutes)
Use demo script for load scenarios:
```bash
./demo-scenarios.sh
```

Good scenarios:
- High CPU usage
- High memory usage
- High MySQL connections

Expected:
- Warnings route to `team-chat-webhook` and warning email.
- Alerts are grouped by `environment/service/severity/alertname`.

### Part 5: Inhibition Behavior (5 minutes)
Send two manual test alerts for same service/instance/environment:

1. Warning alert:
```bash
curl -s -H "Content-Type: application/json" -d '[{
  "labels": {
    "alertname": "SyntheticCapacityWarning",
    "severity": "warning",
    "category": "capacity",
    "service": "mysql",
    "instance": "demo-host",
    "environment": "pilot"
  },
  "annotations": {
    "summary": "Synthetic warning",
    "description": "demo"
  }
}]' http://localhost:9093/api/v2/alerts
```

2. Critical availability alert (same scope):
```bash
curl -s -H "Content-Type: application/json" -d '[{
  "labels": {
    "alertname": "SyntheticAvailabilityCritical",
    "severity": "critical",
    "category": "availability",
    "service": "mysql",
    "instance": "demo-host",
    "environment": "pilot"
  },
  "annotations": {
    "summary": "Synthetic critical",
    "description": "demo"
  }
}]' http://localhost:9093/api/v2/alerts
```

Expected:
- Warning gets inhibited once critical is active for same service/instance/environment.

### Part 6: DBA Requirement Mapping (talk track)
Call out how current PoC maps to daily DBA checks:
- User expiry status: Oracle and MySQL alerts implemented (`OracleUserPasswordExpired`, `OracleUserPasswordExpiryRisk`, `MySQLUserPasswordExpired`, `MySQLUserPasswordExpiryRisk`).
- Tablespace status: Oracle usage alerts implemented (`OracleTablespaceUsageHigh`, `OracleTablespaceUsageCritical`).
- Disk/server load: CPU, memory, disk alerts active.
- DB alert status: Oracle outstanding alert counter monitored.
- Listener status: Oracle/MySQL endpoint probes active.
- Backup freshness: `DatabaseBackupStaleWarning`, `DatabaseBackupStaleCritical` from `db_ops_exporter`.
- Replication health: lag + thread/data guard alerts when replication is configured.
- DB alert-log health: burst + critical event alerts from `db_ops_exporter`.
- MySQL user-expiry and tablespace operational metrics are provided by `db_ops_exporter`.

## Useful Commands

Check active alerts:
```bash
curl -s http://localhost:9091/api/v1/alerts | jq '.data.alerts[] | {name: .labels.alertname, severity: .labels.severity, category: .labels.category, state: .state}'
```

Check rules by group:
```bash
curl -s http://localhost:9091/api/v1/rules | jq '.data.groups[] | {group: .name, rules: [.rules[].name]}'
```

Check listener probe metrics:
```bash
curl -s http://localhost:9091/api/v1/query --data-urlencode 'query=probe_success{job=~"listener_.*"}' | jq
```

Check db_ops metrics:
```bash
curl -s http://localhost:9091/api/v1/query --data-urlencode 'query=db_backup_age_seconds or db_replication_lag_seconds or db_alertlog_error_count_15m' | jq
```

## Troubleshooting

1. Targets down:
- Open `http://localhost:9091/targets`
- Check `docker compose logs <service>` for failing exporter

2. No emails in Mailpit:
- Confirm Mailpit service is running
- Confirm Alertmanager SMTP settings in `alertmanager.yml`

3. Rules not loaded:
- Confirm `prometheus.yml` points to `/etc/prometheus/rules/*.yml`
- Re-run `promtool check config` and `check rules`

4. Oracle panels empty in dashboard:
- Confirm Oracle exporter DSN points to `FREEPDB1` in `docker-compose.yml`.
- Check logs: `docker compose logs --tail=100 oracledb_exporter`
- Confirm Oracle custom metrics load: `oracledb_user_expiry_days_value`, `oracledb_tablespace_usage_value`

5. New dashboard panels show `No data`:
- Run `./simulate-dashboard-activity.sh 10`
- Wait one scrape interval (15-60s) and refresh Grafana

## Cleanup
```bash
docker compose down
```

Remove data volumes:
```bash
docker compose down -v
```
