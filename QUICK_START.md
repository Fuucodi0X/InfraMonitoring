# Quick Start - Alerting Demo

## 1. Start the Stack
```bash
docker-compose up -d
```

## 2. Wait for Services (2-3 minutes)
Check status:
```bash
docker-compose ps
```

## 3. Access UIs
- **Prometheus**: http://localhost:9091
- **Alertmanager**: http://localhost:9093
- **Mailpit** (Email): http://localhost:8025
- **Grafana**: http://localhost:3000 (admin/admin123)

## 4. Run Demo Scenarios
```bash
chmod +x demo-scenarios.sh
./demo-scenarios.sh
```

## 5. Validate Configurations (Optional)
```bash
# If docker-compose is available:
docker-compose config

# Validate Prometheus config (after stack is running):
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml

# Validate Alertmanager config (after stack is running):
docker exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

## What Was Implemented

### Alert Rules (`alert_rules.yml`)
- ✅ Database down detection (Oracle & MySQL)
- ✅ CPU usage alerts (Critical >85%, Warning >70%)
- ✅ Memory usage alerts (Critical >90%, Warning >80%)
- ✅ Oracle active sessions (Critical >100, Warning >75)
- ✅ MySQL connections (Critical >80, Warning >60)
- ✅ Query/Transaction rate alerts
- ✅ Disk space alerts

### Alertmanager (`alertmanager.yml`)
- ✅ Severity-based routing (Critical vs Warning)
- ✅ Service-based routing (Oracle, MySQL, Infrastructure)
- ✅ Alert grouping to reduce email volume
- ✅ Inhibition rules (suppress warnings when critical exists)
- ✅ Different repeat intervals (Critical: 30m, Warning: 4h)
- ✅ HTML email templates

### Demo Script (`demo-scenarios.sh`)
- ✅ Scenario 1: Database Down
- ✅ Scenario 2: High CPU Usage
- ✅ Scenario 3: High Memory Usage
- ✅ Scenario 4: High MySQL Connections
- ✅ Scenario 5: High Oracle Sessions (instructions)
- ✅ Scenario 6: Test Alert Routing
- ✅ Scenario 7: Demonstrate Alert Grouping

### Documentation
- ✅ `DEMO_GUIDE.md` - Complete presentation guide
- ✅ `QUICK_START.md` - This file

## Key Features Demonstrated

1. **Alert Fatigue Prevention**
   - Grouping related alerts
   - Different repeat intervals by severity
   - Inhibition rules

2. **Smart Routing**
   - Critical alerts → immediate notification
   - Warning alerts → delayed notification
   - Service-specific teams

3. **Realistic Scenarios**
   - Database availability
   - Resource utilization
   - Connection limits
   - Performance metrics

## Next Steps

1. Review `DEMO_GUIDE.md` for detailed presentation flow
2. Run `./demo-scenarios.sh` to test scenarios
3. Customize email addresses in `alertmanager.yml` if needed
4. Adjust alert thresholds in `alert_rules.yml` based on your environment
