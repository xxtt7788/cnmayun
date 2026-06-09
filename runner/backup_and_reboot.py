#!/usr/bin/env python3
"""
Backup database and reboot server.
Author: Kimi Code CLI Agent
"""
from paramiko import SSHClient, AutoAddPolicy
import time

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

# Quick DB backup
print("=== Creating database backup ===")
backup_path = f"/tmp/china_succession_backup_$(date +%Y%m%d_%H%M%S).sql"
stdin, stdout, stderr = client.exec_command(
    f"echo 'Kclyh8899' | sudo -S bash -c 'pg_dump china_succession > {backup_path} 2>/dev/null && echo \"Backup OK: {backup_path}\" || echo \"Backup failed\"'"
)
print(stdout.read().decode().strip())

# Check backup size
stdin2, stdout2, stderr2 = client.exec_command(f"ls -lh {backup_path} 2>/dev/null || echo 'No backup file'")
print(stdout2.read().decode().strip())

# Reboot
print("\n=== Rebooting server ===")
stdin3, stdout3, stderr3 = client.exec_command("echo 'Kclyh8899' | sudo -S reboot")
print("Reboot command sent")

client.close()

# Wait for server to come back
print("\nWaiting for server to come back online (90s)...")
time.sleep(90)

# Check connectivity
print("Checking connectivity...")
client2 = SSHClient()
client2.set_missing_host_key_policy(AutoAddPolicy())
try:
    client2.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=30)
    print("SSH connection restored ✓")
    
    # Check services
    stdin, stdout, stderr = client2.exec_command("ps aux | grep -E 'uvicorn|caddy' | grep -v grep")
    procs = stdout.read().decode().strip()
    if procs:
        print("\nServices running:")
        for line in procs.split('\n'):
            parts = line.split()
            if len(parts) >= 11:
                print(f"  {parts[10]} (pid={parts[1]})")
    else:
        print("WARNING: No uvicorn/caddy processes found")
    
    # Check HTTP endpoint
    stdin2, stdout2, stderr2 = client2.exec_command("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz || echo '000'")
    code = stdout2.read().decode().strip()
    print(f"\nHealth check: HTTP {code}")
    
    client2.close()
    print("\nServer reboot completed successfully.")
except Exception as e:
    print(f"Server not yet reachable: {e}")
