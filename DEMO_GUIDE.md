# Alertmanager Demo Guide for DB Team

This guide walks you through demonstrating the alerting system with realistic database scenarios and alert fatigue prevention.

## Pre-Demo Setup

### 1. Start the Stack
```bash
docker compose up -d
```

Wait 2-3 minutes for all services to stabilize. Verify all services are running:
```bash
docker compose ps
```

### 2. Open Browser Tabs
Open these URLs in separate tabs for easy switching:
- **Prometheus**: http://localhost:9091
- **Alertmanager**: http://localhost:9093
- **Mailpit** (Email UI): http://localhost:8025
- **Grafana**: http://localhost:3000 (admin/admin123)

### 3. Validate Configuration
```bash
# Validate Prometheus config
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml

# Validate Alertmanager config
docker exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Check if alert rules are loaded
curl http://localhost:9091/api/v1/rules
```

## Demo Flow

### Part 1: Show Normal State (2 minutes)

**What to show:**
1. **Prometheus Targets** (`http://localhost:9091/targets`)
   - All targets should be UP (green)
   - Show: `oracle_db`, `mysql_db`, `node_oracle`, `node_mysql`

2. **Alertmanager** (`http://localhost:9093`)
   - No active alerts
   - Show the empty alert list

3. **Mailpit** (`http://localhost:8025`)
   - Empty inbox
   - Explain this is where all email notifications will appear

**Key Points:**
- "This is our monitoring stack monitoring Oracle and MySQL databases"
- "All systems are healthy - no alerts"

---

### Part 2: Trigger Warning Alert (5-10 minutes)

**Scenario:** Elevated CPU Usage

**Steps:**
1. Run the demo script:
   ```bash
   chmod +x demo-scenarios.sh
   ./demo-scenarios.sh
   ```
   Select option `2` (High CPU Usage)

2. **While waiting (explain):**
   - "We're generating CPU load to simulate a real workload spike"
   - "Warning alerts have a 10-minute evaluation period"
   - "This prevents false positives from temporary spikes"

3. **After 10 minutes, show:**
   - Alert appears in Alertmanager
   - Email in Mailpit with `[WARNING]` subject
   - Explain: Warning alerts have 4-hour repeat interval (alert fatigue prevention)

**Key Points:**
- Warning alerts are less urgent
- Longer evaluation period reduces noise
- Longer repeat interval prevents spam

---

### Part 3: Trigger Critical Alert (2-3 minutes)

**Scenario:** Database Down

**Steps:**
1. In demo script, select option `1` (Database Down)
   - This stops the MySQL exporter

2. **Show in real-time:**
   - Prometheus targets: MySQL exporter goes DOWN (red)
   - Wait 1 minute
   - Alert appears in Alertmanager immediately
   - Email sent to `critical-alerts` receiver

3. **Compare with warning:**
   - Critical alerts: 1-minute evaluation, 30-minute repeat
   - Warning alerts: 10-minute evaluation, 4-hour repeat
   - Critical alerts: Immediate notification (10s group_wait)
   - Warning alerts: Delayed notification (1m group_wait)

**Key Points:**
- Critical alerts fire faster
- Shorter repeat interval for critical issues
- Different email receivers for different severities

---

### Part 4: Show Alert Fatigue Prevention (5 minutes)

**Scenario:** Multiple Related Alerts

**Steps:**
1. Continue CPU load scenario (if still running)
   - Show that `ElevatedCPUUsage` (warning) fires first
   - Then `HighCPUUsage` (critical) fires
   - **Key:** Warning alert disappears when critical fires (inhibition rule)

2. **Demonstrate grouping:**
   - Run scenario `7` (Alert Grouping) from demo script
   - Send 5 alerts with same labels
   - Show in Alertmanager: All grouped together
   - Show in Mailpit: Only ONE email sent

**Key Points:**
- **Inhibition Rules:** Lower severity suppressed when higher exists
- **Grouping:** Related alerts grouped to reduce email volume
- **Group Wait:** 30-second delay allows grouping before first notification

---

### Part 5: Show Service-Specific Routing (3 minutes)

**Scenario:** Database-Specific Alerts

**Steps:**
1. Run scenario `4` (High MySQL Connections)
   - Show alert routes to `mysql-team` receiver
   - Email subject: `[MySQL] MySQLHighConnections`

2. Run scenario `6` (Test Alert Routing)
   - Send test Oracle alert
   - Show routes to `oracle-team` receiver
   - Email subject: `[Oracle] TestCriticalAlert`

**Key Points:**
- Different teams get different alerts
- Oracle team only sees Oracle issues
- MySQL team only sees MySQL issues
- Infrastructure team sees system-level alerts

---

### Part 6: Show Alert Resolution (2 minutes)

**Steps:**
1. Restore MySQL exporter (if stopped)
   - Run scenario `1` again to restore

2. **Show:**
   - Alert disappears from Alertmanager
   - Resolved email sent (if `send_resolved: true`)
   - Prometheus target goes back to UP

**Key Points:**
- System automatically detects resolution
- Teams notified when issues are resolved
- No manual intervention needed

---

## Key Features to Highlight

### 1. Alert Fatigue Prevention
- **Different repeat intervals:**
  - Critical: 30 minutes
  - Warning: 4 hours
- **Grouping:** Related alerts bundled into one email
- **Inhibition:** Lower severity suppressed when higher exists

### 2. Smart Routing
- **Severity-based:** Critical vs Warning routes
- **Service-based:** Oracle, MySQL, Infrastructure teams
- **Custom receivers:** Different email addresses per team

### 3. Timing Controls
- **Group Wait:** Delay before first notification (allows grouping)
- **Group Interval:** Time between grouped alert updates
- **Repeat Interval:** Time between repeated notifications

### 4. Realistic Alerts
- Database connection limits
- CPU/Memory thresholds
- Query/Transaction rates
- Service availability

## Demo Scripts Reference

### Quick Test Commands

**Check alert rules:**
```bash
curl http://localhost:9091/api/v1/rules | jq
```

**Check active alerts:**
```bash
curl http://localhost:9091/api/v1/alerts | jq
```

**Manually trigger test alert:**
```bash
curl -H "Content-Type: application/json" -d '[{
  "labels": {
    "alertname": "TestAlert",
    "severity": "critical",
    "service": "database"
  },
  "annotations": {
    "summary": "Test alert",
    "description": "Testing the system"
  }
}]' http://localhost:9093/api/v2/alerts
```

**Check MySQL connections:**
```bash
docker exec mysql-db mysql -uroot -pdemo123 -e "SHOW PROCESSLIST;" | wc -l
```

**Check Oracle sessions:**
```bash
docker exec oracle-db sqlplus -s system/demo123@FREE <<EOF
SELECT COUNT(*) FROM v\$session WHERE status='ACTIVE' AND type='USER';
EXIT;
EOF
```

## Troubleshooting

### Alerts Not Firing
1. Check Prometheus targets are UP
2. Verify metrics exist: `http://localhost:9091/graph`
3. Check alert rule evaluation: `http://localhost:9091/alerts`
4. Verify Alertmanager is receiving alerts: `http://localhost:9093`

### Emails Not Sending
1. Check Mailpit is running: `docker compose ps mailpit`
2. Check Mailpit UI: `http://localhost:8025`
3. Verify SMTP config in `alertmanager.yml`
4. Check Alertmanager logs: `docker compose logs alertmanager`

### Metrics Not Available
1. Check exporter endpoints:
   - Oracle: `http://localhost:9161/metrics`
   - MySQL: `http://localhost:9104/metrics`
2. Verify Prometheus scrape config
3. Check Prometheus targets page

## Post-Demo Cleanup

```bash
# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes data)
docker compose down -v
```

## Additional Resources

- **Prometheus Query Examples:**
  - CPU: `100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`
  - Memory: `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100`
  - MySQL Connections: `mysql_global_status_threads_connected`
  - Oracle Sessions: `oracledb_sessions_value{status="ACTIVE", type="USER"}`

- **Alertmanager UI Features:**
  - View active alerts
  - View alert history
  - Test inhibition rules
  - View routing tree
