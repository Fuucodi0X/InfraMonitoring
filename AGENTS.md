# Agentic Coding Guide for Infrastructure Monitoring

This repository contains Infrastructure-as-Code (IaC) for monitoring Oracle and MySQL databases using Prometheus, Grafana, and Alertmanager, orchestrated via Docker Compose.

## 1. Build, Run, and Verify

Since this is an IaC project, "build" refers to container orchestration and configuration validation.

### Core Commands
- **Start Stack:** `docker compose up -d --build` (Builds images if necessary and starts detached)
- **Stop Stack:** `docker compose down` (Stops and removes containers)
- **Stop & Clean:** `docker compose down -v` (Stops and removes volumes - WARNING: Destroys data)
- **Validate Config:** `docker compose config` (Checks syntax of the compose file)
- **View Logs:** `docker compose logs -f [service_name]` (Tail logs for debugging)

### Service Verification (Health Checks)
After starting the stack, verify services are accessible on their mapped ports:
- **Grafana:** `http://localhost:3000` (User/Pass: `admin`/`admin` or env var)
- **Prometheus:** `http://localhost:9091` (Note: Mapped to host port 9091, internal 9090)
- **Alertmanager:** `http://localhost:9093`
- **Oracle Exporter:** `http://localhost:9161/metrics`
- **MySQL Exporter:** `http://localhost:9104/metrics`

### Testing Configuration
There are no unit tests. Testing involves:
1. **Linting:** Ensure `docker-compose.yml` and `prometheus.yml` are valid YAML.
2. **Integration Test:**
   - Start the stack.
   - Query Prometheus targets: `curl -s http://localhost:9091/api/v1/targets | grep "health"`
   - Check if targets (`oracle_db`, `mysql_db`) are in "UP" state.

## 2. Code Style & Conventions

### File Formats
- **YAML (`.yml`, `.yaml`):**
  - **Indentation:** 2 spaces.
  - **Lists:** Use hyphens `-` with one space after.
  - **Keys:** Lowercase, snake_case or kebab-case depending on context (e.g., `job_name` for Prometheus, `container_name` for Docker).
- **JSON (`.json`):**
  - **Indentation:** 4 spaces (e.g., Grafana dashboards).
  - **Structure:** Standard JSON syntax, no trailing commas.

### Docker Compose (`docker-compose.yml`)
- **Version:** implied v3 schema.
- **Service Naming:** Use explicit `container_name` to match the service key (e.g., `service: oracle` -> `container_name: oracle-db`).
- **Networking:**
  - Use `network_mode: "service:<name>"` for sidecar exporters (e.g., `node_exporter` sharing namespace with DB).
  - Use internal DNS (service names) for inter-container communication (e.g., `oracle-db:1521`).
- **Persistence:** Use named volumes for database data (`prometheus_data`, `grafana_data`).

### Prometheus (`prometheus.yml`)
- **Scrape Configs:** Group jobs logically.
- **Targets:** Use Docker service names as hostnames.
- **Intervals:** Default scrape interval is `15s`.

### Grafana (`grafana/`)
- **Provisioning:** Use file-based provisioning for datasources and dashboards.
  - `grafana/provisioning/datasources/*.yml`
  - `grafana/provisioning/dashboards/*.yml`
- **Dashboards:** Store JSON models in `grafana/dashboards/`.
- **Edit Workflow:**
  1. Make changes in Grafana UI.
  2. Export JSON model.
  3. Overwrite the file in `grafana/dashboards/`.

## 3. Directory Structure
```
.
├── docker-compose.yml      # Main orchestration file
├── prometheus.yml          # Prometheus scrape configuration
└── grafana/
    ├── dashboards/         # JSON dashboard definitions
    └── provisioning/       # Grafana provisioning configs
        ├── datasources/
        └── dashboards/
```

## 4. Error Handling & Debugging
- **Container Exits:** Check logs (`docker-compose logs <service>`) for startup errors (often DB credentials or connection strings).
- **Missing Metrics:**
  - Check `http://localhost:9091/targets` to see if the exporter is reachable.
  - Verify network connectivity between Prometheus and Exporters using `docker exec`.

## 5. Security Notes
- **Credentials:** Currently, passwords are hardcoded in `docker-compose.yml` (e.g., `demo123`).
  - *Future Improvement:* Move sensitive values to `.env` file or Docker secrets.
- **Ports:** Only expose necessary ports to the host.
