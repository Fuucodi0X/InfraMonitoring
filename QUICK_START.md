# Quick Start - DBA Monitoring PoC

## 1. Prepare Environment Variables
```bash
cp .env.example .env
```

Update `.env` values before running in a shared environment.

## 2. Start the Stack
```bash
docker compose up -d
```

## 3. Verify Services
```bash
docker compose ps
```

## 4. Access UIs
- **Grafana:** http://localhost:3000
- **Prometheus:** http://localhost:9091
- **Alertmanager:** http://localhost:9093
- **Mailpit (email sink):** http://localhost:8025
- **Alert webhook sink:** http://localhost:8080

## 5. Validate Configurations
```bash
# Compose
docker compose config

# Prometheus config + rules
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker exec prometheus promtool check rules /etc/prometheus/rules/*.yml

# Alertmanager
docker exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

## 6. Verify Monitoring Coverage
```bash
# Scrape targets
curl -s http://localhost:9091/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Loaded alert rules
curl -s http://localhost:9091/api/v1/rules | jq '.data.groups[].name'

# Active alerts
curl -s http://localhost:9091/api/v1/alerts | jq '.data.alerts[] | {name: .labels.alertname, state: .state}'
```

## Implemented Architecture (Current)

### Stack
- Prometheus + Alertmanager + Grafana
- Oracle + MySQL exporters
- Node exporter for host metrics
- Blackbox exporter for listener endpoint checks
- Mailpit for demo email notifications
- Alert webhook sink for pager/chat route simulation

### Rule Packs
- `rules/availability.yml`
- `rules/operational.yml`
- `rules/security.yml`
- `rules/capacity.yml`
- `rules/performance.yml`

### Label and Alert Contract
- Target labels include: `environment`, `team`, `owner`, `service`, `db_engine`, `db_role`
- Alerts include: `severity`, `category`, `service`, `db_engine`, `team`, `owner`
- Annotations include: `summary`, `description`, `impact`, `action`, `runbook_url`

### Key Alert Coverage
- DB availability: `OracleDatabaseDown`, `MySQLDatabaseDown`
- Listener health: `OracleListenerDown`, `MySQLListenerDown`
- User expiry/security: `OracleUserPasswordExpired`, `OracleUserPasswordExpiryRisk`, `MySQLPasswordPolicyDisabled`
- Capacity: CPU, memory, disk, Oracle tablespace high/critical
- Performance: MySQL connection utilization, Oracle active sessions

### Alert Routing
- Critical availability/operational alerts -> `pager-webhook`
- Warning alerts -> `team-chat-webhook`
- Email receivers remain active for critical/warning and engine-specific fanout
- Inhibition suppresses warning when matching critical is active

## Demo Scenarios
Use:
```bash
./demo-scenarios.sh
```

Note: some script prompts still reference legacy alert names/credentials. The stack configuration and rule files are the source of truth.

## Shutdown
```bash
docker compose down
```

To remove volumes too:
```bash
docker compose down -v
```
