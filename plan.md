## Assessment and Upgrade Plan: Database-Centric Monitoring With Low-Noise Alerting

### Summary
Current project fulfillment of stated goal (centralized monitoring + actionable alerts with low fatigue): **~65/100**.

- **What is strong now**
1. Centralized stack exists (Prometheus + Alertmanager + Grafana).
2. Multi-DB coverage (Oracle + MySQL) is implemented.
3. Alert fatigue controls are partially present (grouping, inhibition, severity routing).

- **What limits goal fulfillment**
1. Alert rules are mostly static-threshold and not SLO/symptom-driven, which can still produce noise.
2. No formal ownership/runbook metadata in alerts (harder triage).
3. Single-node local architecture (no HA/ruler separation/long-term scaling path).
4. Security posture is demo-grade (hardcoded credentials).
5. Notification model is email-centric only; no explicit paging/escalation model.

### Evidence From Current Repo
1. Stack and service topology: `docker-compose.yml`
2. Scrape and rule loading: `prometheus.yml`
3. Alert definitions: `alert_rules.yml`
4. Routing/inhibition: `alertmanager.yml`
5. Dashboard provisioning: `grafana/provisioning/datasources/datasources.yml`, `grafana/provisioning/dashboards/dashboards.yml`

### Recommended Tech Stack (Open-Source Self-Hosted, Production-Ready Baseline)
1. **Metrics + Alerting Core**
   - Prometheus (or VictoriaMetrics single/cluster) for scraping
   - Alertmanager for routing/inhibition/silences
   - Grafana for visualization + unified alert UI (optional)
2. **Scalability + Retention**
   - Add `remote_write` to **Mimir** or **Thanos** for centralized long-term metrics
3. **Meta-monitoring**
   - Blackbox exporter for synthetic checks (DB endpoint reachability)
   - Keep node + DB exporters, but add label normalization
4. **Incident Workflow**
   - Alertmanager routes to:
     - paging channel (critical, symptom-based)
     - ticket/chat channel (warning/capacity)
   - Keep email as secondary notification, not primary for urgent pages
5. **Governance**
   - Rule linting/tests via `promtool test rules`
   - Runbook links and owner labels mandatory in every alert

### Better Approach for Alert Fatigue (Policy)
1. Page only on **symptoms** (down, sustained latency/error, replication failure risk).
2. Route capacity/early-warning alerts as non-page notifications.
3. Use multi-window burn-rate style alerts where possible instead of raw thresholds.
4. Add `for` windows based on service criticality and business hours policy.
5. Enforce inhibition hierarchy by `severity`, `service`, `instance`, and `environment`.

### Important Public Interfaces / Contracts to Add
1. **Alert label schema (mandatory)**
   - `severity`, `service`, `database`, `environment`, `team`, `owner`, `runbook_url`
2. **Alert annotation schema**
   - `summary`, `description`, `impact`, `action`
3. **Routing contract**
   - Critical symptom alerts -> `oncall-pager`
   - Warning/capacity -> `team-chat` / `ticket`
4. **Dashboard contract**
   - Folder by service (`oracle`, `mysql`, `infrastructure`)
   - Required top panels: availability, latency, saturation, error/health, alert status

### Implementation Plan (Decision-Complete)
1. **Classify existing alerts into symptom vs capacity**
   - Keep: DB down alerts as paging candidates.
   - Reclassify CPU/memory/query-rate/session/connection as non-page unless tied to user impact.
2. **Refactor rule set into layered groups**
   - `availability.yml`, `performance.yml`, `capacity.yml`, `security.yml`
   - Add runbook and owner metadata to every rule.
3. **Harden Alertmanager routing**
   - Top-level route by `environment` + `severity`.
   - Critical only to pager receiver.
   - Warnings to chat/ticket with longer repeat intervals.
4. **Introduce baseline SLO-style rules**
   - DB endpoint availability objective
   - Query latency/error surrogate for MySQL and Oracle exporter metrics
5. **Security uplift**
   - Move credentials into `.env`/secrets
   - Remove root DB user for Grafana datasource (least privilege account)
6. **Scale path**
   - Add `remote_write` (Mimir/Thanos/VictoriaMetrics) and retention policy
   - Define central multi-environment labeling convention
7. **Operational readiness**
   - Add rule unit tests + config validation in CI
   - Add “meta-monitoring” alerts for Prometheus/Alertmanager health

### Test Cases and Acceptance Scenarios
1. **Noise reduction**
   - Trigger 5 related warning alerts; verify grouped delivery and no paging.
2. **Severity correctness**
   - Trigger DB-down; verify pager route within defined SLA.
3. **Inhibition correctness**
   - Trigger warning + critical for same service/instance; warning suppressed.
4. **Actionability**
   - Each fired alert includes runbook URL, owner/team, and immediate action.
5. **Resilience**
   - Prometheus restart does not lose central history (remote storage validates continuity).
6. **Security**
   - No plaintext credentials in tracked config files.

### Assumptions and Defaults Chosen
1. Scope selected: **Production-ready baseline**.
2. Ops model selected: **Open-source self-hosted**.
3. Default policy: email remains informational; paging is used for critical symptom alerts only.
4. Environment model assumed: at least dev/stage/prod, requiring explicit `environment` label in all targets/rules.
