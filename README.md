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

## 🛠️ Technology Stack

*   **Core**: [Prometheus](https://prometheus.io/) (Metrics Collection) & [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) (Incident Lifecycle)
*   **Visualization**: [Grafana](https://grafana.com/)
*   **Testing**: [Mailpit](https://github.com/axllent/mailpit) (Local SMTP Server/UI)
*   **Databases**: Oracle Free (slim) & MySQL 8.0
*   **Exporters**: Node Exporter, MySQLD Exporter, OracleDB Exporter
*   **Ops Collector**: `db_ops_exporter` for backup/replication/alert-log summary metrics

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

## 📂 Project Structure

*   `docker-compose.yml`: Orchestrates the entire stack and network.
*   `prometheus.yml`: Scrape configurations and target definitions.
*   `alert_rules.yml`: The logic for CPU, Memory, Disk, and Database health alerts.
*   `alertmanager.yml`: Routing trees, inhibition rules, and receiver configuration.
*   `demo-scenarios.sh`: Interactive script to simulate infrastructure stress.
*   `grafana/`: contains datasource and dashboard provisioning.

## 📖 Documentation
For more detailed information, see:
*   [QUICK_START.md](./QUICK_START.md) - Fast-track setup instructions.
*   [DEMO_GUIDE.md](./DEMO_GUIDE.md) - A step-by-step guide for presenting this stack.

---
*Created as a demonstration for Infrastructure and DBA teams to showcase modern observability patterns.*
