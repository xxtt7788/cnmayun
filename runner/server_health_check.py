#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

print("=== Server Health Check ===\n")

# Disk usage
print("--- Disk Usage ---")
stdin, stdout, stderr = client.exec_command("df -h | grep -E 'Filesystem|/dev/vda'")
print(stdout.read().decode().strip())

# Memory usage
print("\n--- Memory Usage ---")
stdin2, stdout2, stderr2 = client.exec_command("free -h")
print(stdout2.read().decode().strip())

# CPU load
print("\n--- CPU Load ---")
stdin3, stdout3, stderr3 = client.exec_command("uptime")
print(stdout3.read().decode().strip())

# Large log files
print("\n--- Large Log Files (>10MB) ---")
stdin4, stdout4, stderr4 = client.exec_command(
    "find /opt/china-succession/runner -name '*.log' -size +10M -exec ls -lh {} \; 2>/dev/null || echo 'No large logs'"
)
print(stdout4.read().decode().strip())

# Check uvicorn log for errors
print("\n--- Uvicorn Recent Errors ---")
stdin5, stdout5, stderr5 = client.exec_command(
    "sudo journalctl -u china-succession --since '1 hour ago' --no-pager 2>/dev/null | grep -i error | tail -5 || echo 'No recent errors'"
)
print(stdout5.read().decode().strip())

# Check PostgreSQL connections
print("\n--- PostgreSQL Connections ---")
stdin6, stdout6, stderr6 = client.exec_command(
    "sudo -u postgres psql -c 'SELECT count(*) FROM pg_stat_activity;' 2>/dev/null || echo 'Cannot query PG'"
)
print(stdout6.read().decode().strip())

# List all log files in runner
print("\n--- Runner Log Files ---")
stdin7, stdout7, stderr7 = client.exec_command(
    "ls -lh /opt/china-succession/runner/*.log 2>/dev/null | awk '{print $5, $9}' || echo 'No log files'"
)
print(stdout7.read().decode().strip())

client.close()
