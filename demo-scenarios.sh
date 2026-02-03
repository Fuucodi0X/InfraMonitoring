#!/bin/bash
# demo-scenarios.sh - Script to trigger different alert scenarios for DB team demo

set -e

echo "=== Database Monitoring Demo Scenarios ==="
echo ""

# Function to check if services are running
check_services() {
    echo "Checking services..."
    docker compose ps
    echo ""
}

# Function to wait for user input
wait_for_user() {
    echo "Press Enter to continue..."
    read
}

# Scenario 1: Stop MySQL exporter (DatabaseDown alert)
scenario_1() {
    echo "=== Scenario 1: Database Down ==="
    echo "Stopping MySQL exporter to trigger DatabaseDown alert..."
    docker compose stop mysqld_exporter
    echo ""
    echo "✓ MySQL exporter stopped"
    echo "  - Wait 1-2 minutes for alert to trigger"
    echo "  - Check Alertmanager UI: http://localhost:9093"
    echo "  - Check Mailpit: http://localhost:8025"
    echo "  - Check Prometheus targets: http://localhost:9091/targets"
    wait_for_user
    echo "Restoring MySQL exporter..."
    docker compose start mysqld_exporter
    echo "✓ MySQL exporter restored. Alert should resolve in 1-2 minutes."
    echo ""
}

# Scenario 2: Generate high CPU load
scenario_2() {
    echo "=== Scenario 2: High CPU Usage ==="
    echo "Generating CPU load on Oracle container..."
    
    # Start background processes to generate CPU load
    docker exec -d oracle-db sh -c "while true; do dd if=/dev/zero of=/dev/null 2>/dev/null & done"
    
    echo "✓ High CPU load generated (background processes started)"
    echo "  - Wait 5-10 minutes for alerts to trigger"
    echo "  - Check Prometheus: http://localhost:9091/graph?g0.expr=100%20-%20(avg%20by(instance)%20(rate(node_cpu_seconds_total%7Bmode%3D%22idle%22%7D%5B5m%5D))%20*%20100)"
    echo "  - Check Alertmanager: http://localhost:9093"
    echo "  - Note: ElevatedCPUUsage (warning) should trigger first, then HighCPUUsage (critical)"
    echo "  - Note: Inhibition rule should suppress warning when critical fires"
    wait_for_user
    
    echo "Stopping CPU load..."
    docker exec oracle-db sh -c "pkill -f 'dd if=/dev/zero' || true"
    docker exec oracle-db sh -c "killall dd 2>/dev/null || true"
    echo "✓ CPU load stopped. Alerts should resolve."
    echo ""
}

# Scenario 3: Generate high memory usage
scenario_3() {
    echo "=== Scenario 3: High Memory Usage ==="
    echo "Generating memory pressure on MySQL container..."
    
    # Try to allocate memory using Python or fallback to simple method
    docker exec -d mysql-db sh -c "
        python3 -c \"
import time
data = []
try:
    for i in range(10):
        data.append(bytearray(100*1024*1024))  # 100MB chunks
        time.sleep(1)
    time.sleep(300)  # Hold for 5 minutes
except:
    pass
\" 2>/dev/null || 
    python -c \"
import time
data = []
try:
    for i in range(10):
        data.append(bytearray(100*1024*1024))
        time.sleep(1)
    time.sleep(300)
except:
    pass
\" 2>/dev/null || 
    echo 'Python not available, using alternative method...'
    " || echo "Memory load script started"
    
    echo "✓ Memory pressure generated"
    echo "  - Wait 5-10 minutes for alerts to trigger"
    echo "  - Check Prometheus memory metrics"
    echo "  - Check Alertmanager for memory alerts"
    wait_for_user
    
    echo "Cleaning up memory load..."
    docker exec mysql-db sh -c "pkill -f python || true"
    echo "✓ Memory load stopped."
    echo ""
}

# Scenario 4: Simulate high database connections (MySQL)
scenario_4() {
    echo "=== Scenario 4: High MySQL Connections ==="
    echo "Opening multiple MySQL connections..."
    
    # Open connections in background
    for i in {1..100}; do
        docker exec -d mysql-db mysql -uroot -pdemo123 -e "SELECT SLEEP(300);" 2>/dev/null &
    done
    
    echo "✓ 100 MySQL connections opened"
    echo "  - Wait 5 minutes for alert to trigger"
    echo "  - Check current connections: docker exec mysql-db mysql -uroot -pdemo123 -e 'SHOW PROCESSLIST;' | wc -l"
    echo "  - Check Alertmanager: http://localhost:9093"
    echo "  - Check Mailpit: http://localhost:8025"
    wait_for_user
    
    echo "Closing MySQL connections..."
    docker exec mysql-db mysqladmin -uroot -pdemo123 kill all 2>/dev/null || true
    echo "✓ Connections closed. Alert should resolve."
    echo ""
}

# Scenario 5: Simulate high Oracle sessions
scenario_5() {
    echo "=== Scenario 5: High Oracle Active Sessions ==="
    echo "Creating multiple Oracle sessions..."
    echo ""
    echo "Note: This requires SQL scripts. Here's how to do it manually:"
    echo ""
    echo "1. Connect to Oracle:"
    echo "   docker exec -it oracle-db sqlplus system/demo123@FREE"
    echo ""
    echo "2. Run this SQL to create sessions:"
    echo "   BEGIN"
    echo "     FOR i IN 1..100 LOOP"
    echo "       EXECUTE IMMEDIATE 'BEGIN NULL; END;';"
    echo "     END LOOP;"
    echo "   END;"
    echo "   /"
    echo ""
    echo "Or use a script file:"
    echo "   docker exec -i oracle-db sqlplus system/demo123@FREE @/path/to/script.sql"
    echo ""
    echo "Alternative: Use multiple sqlplus connections in parallel"
    wait_for_user
    echo ""
}

# Scenario 6: Test alert routing
scenario_6() {
    echo "=== Scenario 6: Test Alert Routing ==="
    echo "Sending test alerts via Alertmanager API..."
    echo ""
    
    # Test critical alert
    echo "1. Sending CRITICAL test alert..."
    curl -s -H "Content-Type: application/json" -d '[{
      "labels": {
        "alertname": "TestCriticalAlert",
        "severity": "critical",
        "service": "oracle",
        "instance": "test-instance"
      },
      "annotations": {
        "summary": "This is a test critical alert",
        "description": "Testing critical alert routing to oracle-team receiver"
      }
    }]' http://localhost:9093/api/v2/alerts > /dev/null
    echo "   ✓ Critical alert sent"
    echo "   - Check Mailpit: http://localhost:8025"
    echo "   - Should route to: oracle-team receiver"
    sleep 2
    
    # Test warning alert
    echo ""
    echo "2. Sending WARNING test alert..."
    curl -s -H "Content-Type: application/json" -d '[{
      "labels": {
        "alertname": "TestWarningAlert",
        "severity": "warning",
        "service": "mysql",
        "instance": "test-instance"
      },
      "annotations": {
        "summary": "This is a test warning alert",
        "description": "Testing warning alert routing to mysql-team receiver"
      }
    }]' http://localhost:9093/api/v2/alerts > /dev/null
    echo "   ✓ Warning alert sent"
    echo "   - Check Mailpit: http://localhost:8025"
    echo "   - Should route to: mysql-team receiver"
    echo "   - Note: Warning alerts have longer group_wait (1m) and repeat_interval (4h)"
    wait_for_user
    echo ""
}

# Scenario 7: Show alert grouping
scenario_7() {
    echo "=== Scenario 7: Demonstrate Alert Grouping ==="
    echo "Sending multiple related alerts to show grouping..."
    echo ""
    
    for i in {1..5}; do
        curl -s -H "Content-Type: application/json" -d "[{
          \"labels\": {
            \"alertname\": \"GroupedAlert\",
            \"severity\": \"warning\",
            \"service\": \"infrastructure\",
            \"instance\": \"instance-$i\"
          },
          \"annotations\": {
            \"summary\": \"Grouped alert instance $i\",
            \"description\": \"This alert should be grouped with others\"
          }
        }]" http://localhost:9093/api/v2/alerts > /dev/null
        echo "   Sent alert $i/5..."
        sleep 1
    done
    
    echo ""
    echo "✓ 5 alerts sent with same service/severity/alertname"
    echo "  - Check Alertmanager: http://localhost:9093"
    echo "  - All alerts should be grouped together"
    echo "  - Only ONE email should be sent (grouped)"
    echo "  - Check Mailpit: http://localhost:8025"
    wait_for_user
    echo ""
}

# Main menu
main() {
    check_services
    
    while true; do
        echo "=========================================="
        echo "Select a scenario to run:"
        echo "1) Database Down (MySQL exporter)"
        echo "2) High CPU Usage"
        echo "3) High Memory Usage"
        echo "4) High MySQL Connections"
        echo "5) High Oracle Sessions (manual instructions)"
        echo "6) Test Alert Routing"
        echo "7) Demonstrate Alert Grouping"
        echo "8) Run all scenarios sequentially"
        echo "0) Exit"
        echo "=========================================="
        read -p "Enter choice: " choice
        echo ""
        
        case $choice in
            1) scenario_1 ;;
            2) scenario_2 ;;
            3) scenario_3 ;;
            4) scenario_4 ;;
            5) scenario_5 ;;
            6) scenario_6 ;;
            7) scenario_7 ;;
            8) 
                scenario_1
                scenario_2
                scenario_3
                scenario_4
                scenario_5
                scenario_6
                scenario_7
                ;;
            0) 
                echo "Exiting demo script..."
                exit 0 
                ;;
            *) 
                echo "Invalid choice. Please try again."
                echo ""
                ;;
        esac
    done
}

main
