# InfraMonitoring: Advanced Database Alerting & Observation

A comprehensive, production-inspired monitoring stack designed to demonstrate smart observability and alert fatigue prevention for mixed database environments (Oracle & MySQL).

## 🚀 Overview

This project provides a fully containerized environment that showcases how to build a resilient monitoring pipeline. It doesn't just collect metrics; it implements a sophisticated alerting strategy that distinguishes between "warnings" and "critical failures," routes alerts to specific teams, and uses inhibition rules to keep noise levels low.

### 🎯 Objective
*   **Visibility**: Real-time health monitoring of Oracle and MySQL instances.
*   **Precision**: Smart alerting thresholds that minimize false positives.
*   **Efficiency**: Preventing alert fatigue through grouping and inhibition.
*   **Education**: A safe sandbox to experiment with Prometheus and Alertmanager configurations.
*   **Operations**: Daily DBA checks including user expiry, tablespace, listener, backup freshness, replication lag, and alert-log health.
*   **Demoability**: Built-in simulation workflow to populate realistic dashboard activity data on demand.

## 🛠️ Technology Stack

*   **Core**: [Prometheus](https://prometheus.io/) (Metrics Collection) & [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) (Incident Lifecycle)
*   **Visualization**: [Grafana](https://grafana.com/)
*   **Testing**: [Mailpit](https://github.com/axllent/mailpit) (Local SMTP Server/UI)
*   **Databases**: Oracle Free (slim) & MySQL 8.0
*   **Exporters**: Node Exporter, MySQLD Exporter, OracleDB Exporter
*   **Ops Collector**: `db_ops_exporter` for backup/replication/alert-log plus MySQL user-expiry and tablespace summary metrics

## 🏗️ Smart Alerting Features

### 1. Severity-Based Routing
The system distinguishes between **Warning** and **Critical** events:
*   **Critical alerts** (e.g., Database Down) fire within 1 minute and repeat every 30 minutes.
*   **Warning alerts** (e.g., Elevated CPU) wait for 10 minutes to ensure the issue is persistent and only repeat every 4 hours.

### 2. Alert Fatigue Management
*   **Inhibition Rules**: Automatically silences warning-level alerts if a critical alert is already active for the same service.
*   **Grouping**: Bundles related alerts into a single notification to avoid "inbox storms" during major outages.
*   **Service Routing**: Automatically directs alerts to the `oracle-team`, `mysql-team`, or `infra-team` based on the resource labels.

## 🚦 Quick Start

### 1. Deploy the Stack
```bash
docker compose up -d
```

### 2. Access the Dashboards
*   **Grafana**: [http://localhost:3000](http://localhost:3000) (User/Pass: `admin/admin123`)
*   **Prometheus**: [http://localhost:9091](http://localhost:9091)
*   **Alertmanager**: [http://localhost:9093](http://localhost:9093)
*   **Mailpit (Email UI)**: [http://localhost:8025](http://localhost:8025)

### 3. Run Demo Scenarios
Trigger real-world failures to see the alerting logic in action:
```bash
./demo-scenarios.sh
```

Populate activity data for the comprehensive DBA dashboard:
```bash
./simulate-dashboard-activity.sh 10
```
(`10` = minutes of live write simulation)

## 📂 Project Structure

*   `docker-compose.yml`: Orchestrates the entire stack and network.
*   `prometheus.yml`: Scrape configurations and target definitions.
*   `alert_rules.yml`: The logic for CPU, Memory, Disk, and Database health alerts.
*   `alertmanager.yml`: Routing trees, inhibition rules, and receiver configuration.
*   `demo-scenarios.sh`: Interactive script to simulate infrastructure stress.
*   `simulate-dashboard-activity.sh`: Seeds MySQL user/backup/tablespace activity for dashboard demos.
*   `grafana/`: contains datasource and dashboard provisioning.

## 📊 Dashboards

Grafana includes:
*   `Database Proactive Monitoring` (existing broad dashboard)
*   `DBA Operations Comprehensive` (new day-to-day DBA dashboard)

The new dashboard is focused on:
*   User expiry and account health
*   Backup freshness/status
*   Replication lag/status
*   Tablespace utilization
*   Disk/host health
*   DB server and listener status
*   DB alert trends

## 🔧 Oracle Exporter Compatibility Notes

For Oracle Free images in this repo:
*   Oracle exporter DSN uses `FREEPDB1` service.
*   Custom tablespace metric query in `oracledb_exporter/custom-metrics.toml` uses only compatible columns from `dba_tablespace_usage_metrics`.

## 📖 Documentation
For more detailed information, see:
*   [QUICK_START.md](./QUICK_START.md) - Fast-track setup instructions.
*   [DEMO_GUIDE.md](./DEMO_GUIDE.md) - A step-by-step guide for presenting this stack.

---
*Created as a demonstration for Infrastructure and DBA teams to showcase modern observability patterns.*
