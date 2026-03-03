# PoC Plan: Centralized DBA Monitoring and Low-Noise Alerting (Oracle + MySQL)

## Summary
This repo is a strong **foundation** for your objective, but currently it is still a **demo-oriented stack**.

### What you already used well
- Prometheus + Alertmanager + Grafana is the right core stack for centralized monitoring.
- Oracle + MySQL exporters are wired and scraping.
- Alertmanager grouping/routing/inhibition is already implemented and is a good start against alert fatigue.
- Grafana dashboards already include useful operational panels and user-expiry visibility.

### What is missing vs your DBA day-to-day requirements
- No alert rules yet for:
  - user expiry risk
  - tablespace usage risk
  - listener status
  - DB internal alert/log status
- Disk/server checks are present but basic; need predictive and severity policy.
- Current alerts are mostly static-threshold; not yet symptom-first (too noisy for operations).
- Credentials are hardcoded (not acceptable for prod-like pilot).
- Notification model is email-centric; critical incidents need real-time channel.

Decision: **keep the current tech stack**, do not replace it for PoC. Upgrade it into an ops-grade pilot design.

## Scope and Defaults (Locked)
- Scope: **Prod-like pilot** (5-20 DB servers pattern).
- Engines: **Oracle + MySQL only**.
- Collection model: **Exporter-based SQL checks**.
- Listener health: **host process/socket check**.
- Secrets baseline: **`.env` + least-privilege DB users**.
- Critical notification: **pager/chat + email fallback**.

## Architecture and Interface Changes

### 1. Target Label Contract (mandatory on all scrape targets)
Add and enforce labels:
- `environment` (`pilot`)
- `team` (`dba`)
- `db_engine` (`oracle|mysql`)
- `db_role` (`primary|standby|replica`)
- `service` (`oracle|mysql|infra`)
- `owner` (`dba-team`)

### 2. Alert Label/Annotation Contract (mandatory on all rules)
Labels:
- `severity` (`critical|warning|info`)
- `service`, `db_engine`, `environment`, `team`, `owner`
- `category` (`availability|capacity|security|performance|operational`)

Annotations:
- `summary`
- `description`
- `impact`
- `action`
- `runbook_url`

### 3. Rule File Structure
Split `alert_rules.yml` into:
- `rules/availability.yml`
- `rules/capacity.yml`
- `rules/security.yml`
- `rules/operational.yml`
- `rules/performance.yml`

### 4. Alert Routing Contract (Alertmanager)
- `critical` + `availability|operational` -> pager/chat receiver.
- `warning`/capacity/performance -> team chat or ticket receiver.
- Email remains fallback/informational.
- Keep inhibition hierarchy:
  - critical inhibits warning on same `service + instance`.
  - availability inhibits derivative capacity alerts for same target.

## Requirement Coverage Plan (Your DBA Tasks)

### User expiry date status
- Oracle: keep exporter custom query; add alert:
  - critical if expired users > 0 for non-exempt accounts.
  - warning if `days_until_expiry <= 7`.
- MySQL: add equivalent metric collection and alerts for expiring/expired users.

### Tablespace status
- Oracle: add exporter query for tablespace usage %, free space, autoextend risk.
- MySQL: monitor filesystem/datadir free space + InnoDB growth.
- Alerts:
  - warning at 85%, critical at 95%, plus predictive “time-to-full” warning.

### Disk health & space status
- Keep node exporter metrics; add:
  - filesystem inode alert
  - disk read/write error trend (where available)
  - predictive fill alerts (already partly in dashboard, formalize as alerts).

### Server load status
- Replace simple CPU-only logic with composite signals:
  - sustained load/core ratio
  - CPU saturation
  - memory pressure
  - swap pressure (if enabled).

### DB alert status
- Oracle: add exporter SQL for alert log/event summary counters.
- MySQL: alert/event log counters where exporter supports; otherwise staged as “phase 2” via controlled custom collector.
- Alert only on actionable/high-severity classes.

### Listener status
- Add listener check metric via host-level process/socket probe.
- Alert when listener down for >1m (critical).

## Tech Stack Critique and Decision
- Keep: Prometheus, Alertmanager, Grafana, exporters.
- Do not change stack for PoC; change **operating model**:
  - from demo thresholds -> actionability policy
  - from email-only -> real-time incident channel
  - from hardcoded creds -> `.env` and least privilege
  - from monolithic rules -> categorized, testable rule packs

Optional next-stage (not required for PoC): long-term retention via Thanos/Mimir/VictoriaMetrics.

## Implementation Work Packages (Decision-Complete)

1. **Security baseline**
- Move all credentials from `docker-compose.yml` to `.env`.
- Create read-only monitor users for Oracle/MySQL.
- Remove root-based scraping path.

2. **Metric expansion**
- Extend Oracle custom metrics for tablespaces and DB alerts.
- Add MySQL equivalents for user expiry/security and operational status.
- Add listener process/socket check metric.

3. **Rule redesign**
- Create rule packs by category.
- Add severity policy + `for` windows tuned for noise reduction.
- Add mandatory labels/annotations/runbook metadata.

4. **Alertmanager redesign**
- Add receiver routing for pager/chat (critical) and chat/ticket (warning).
- Keep grouping/inhibition and tighten matcher scope using new labels.

5. **Dashboard alignment**
- Create DBA operations dashboard sections:
  - availability
  - user expiry/security
  - storage/tablespace
  - listener/operational health
  - active alerts and suppression visibility.

6. **Quality gates**
- Add config/rule validation commands to CI:
  - `docker compose config`
  - `promtool check config`
  - `promtool check rules`
  - `amtool check-config`

## Test Cases and Acceptance Criteria

1. **Coverage test**
- Every listed DBA task has at least one metric panel and one alert (or explicit deferred note).

2. **Noise test**
- Simulate warning+critical same entity; warning is inhibited.

3. **Routing test**
- Critical DB-down reaches pager/chat path within target SLA.
- Warning capacity alert routes only to non-paging channel.

4. **Actionability test**
- Fired alert includes owner, runbook URL, impact, and action.

5. **Security test**
- No hardcoded credentials remain in tracked configs.

6. **PoC readiness test**
- Demonstrate Oracle + MySQL instances in one dashboard with role/environment labels and filtered alert views.

## Assumptions
- PoC environment allows chat/pager integration endpoint (or mock webhook).
- DBA team can provide threshold baselines per DB class within pilot window.
- Listener checks can run on monitored hosts with required visibility.
