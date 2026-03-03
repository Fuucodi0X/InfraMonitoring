#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing .env file"
  exit 1
fi

set -a
source .env
set +a

MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-change_me}"
SIM_MINUTES="${1:-10}"

log() {
  echo "[$(date +'%H:%M:%S')] $*"
}

mysql_exec() {
  docker exec -i mysql-db mysql -uroot "-p${MYSQL_ROOT_PASSWORD}" -e "$1"
}

log "Rebuilding/restarting exporters so latest metrics are active"
docker compose up -d --build db-ops-exporter oracledb_exporter

log "Seeding MySQL demo accounts (expired/expiring/locked)"
mysql_exec "
CREATE USER IF NOT EXISTS 'demo_expired'@'%' IDENTIFIED BY 'DemoPass#123';
ALTER USER 'demo_expired'@'%' PASSWORD EXPIRE;

CREATE USER IF NOT EXISTS 'demo_expiring_soon'@'%' IDENTIFIED BY 'DemoPass#123' PASSWORD EXPIRE INTERVAL 5 DAY;
CREATE USER IF NOT EXISTS 'demo_expiring_month'@'%' IDENTIFIED BY 'DemoPass#123' PASSWORD EXPIRE INTERVAL 20 DAY;

CREATE USER IF NOT EXISTS 'demo_locked'@'%' IDENTIFIED BY 'DemoPass#123' ACCOUNT LOCK;

FLUSH PRIVILEGES;
"

log "Seeding backup metadata used by db_ops_exporter"
mysql_exec "
CREATE TABLE IF NOT EXISTS mysql.backup_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  end_time DATETIME NOT NULL,
  exit_state VARCHAR(32) NOT NULL,
  backup_type VARCHAR(32) DEFAULT 'full'
);

INSERT INTO mysql.backup_history (end_time, exit_state, backup_type)
VALUES
  (NOW() - INTERVAL 2 HOUR, 'SUCCESS', 'incremental'),
  (NOW() - INTERVAL 26 HOUR, 'SUCCESS', 'full'),
  (NOW() - INTERVAL 30 MINUTE, 'FAILED', 'incremental');
"

log "Creating MySQL schema/tablespace workload data"
mysql_exec "
CREATE DATABASE IF NOT EXISTS demo_workload;
CREATE TABLE IF NOT EXISTS demo_workload.events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"

log "Loading baseline rows (about 30k)"
docker exec -i mysql-db mysql -uroot "-p${MYSQL_ROOT_PASSWORD}" <<'SQL'
USE demo_workload;
INSERT INTO events (payload)
SELECT CONCAT('dashboard-demo-', t.n, '-', REPEAT('x', 120))
FROM (
  SELECT @row := @row + 1 AS n
  FROM information_schema.columns c1
  CROSS JOIN information_schema.columns c2
  CROSS JOIN (SELECT @row := 0) init
  LIMIT 30000
) AS t;
SQL

log "Running write simulation for ${SIM_MINUTES} minute(s)"
end_epoch=$(( $(date +%s) + SIM_MINUTES * 60 ))
while [[ $(date +%s) -lt $end_epoch ]]; do
  docker exec -i mysql-db mysql -uroot "-p${MYSQL_ROOT_PASSWORD}" <<'SQL' >/dev/null
USE demo_workload;
INSERT INTO events (payload)
SELECT CONCAT('live-activity-', UUID(), '-', REPEAT('y', 150))
FROM information_schema.columns
LIMIT 500;
SQL
  sleep 5
done

log "Simulation complete"
log "Validate in Prometheus: http://localhost:9091"
log "Validate dashboard: http://localhost:3000/d/dba-ops-comprehensive/dba-operations-comprehensive"
