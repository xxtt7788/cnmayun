#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

print("=== Processes ===")
for name in ['backfill_company_location_v3', 'backfill_tenure_start_dates']:
    stdin, stdout, stderr = client.exec_command(f"ps aux | grep {name} | grep -v grep | wc -l")
    count = stdout.read().decode().strip()
    print(f"  {name}: {count} running")

print("\n=== Location V3 Log (last 5) ===")
stdin, stdout, stderr = client.exec_command(
    "tail -5 /opt/china-succession/runner/backfill_company_location_v3.log 2>/dev/null || echo 'No log'"
)
print(stdout.read().decode().strip())

print("\n=== Tenure Start Log (last 5) ===")
stdin, stdout, stderr = client.exec_command(
    "tail -5 /opt/china-succession/runner/backfill_tenure_start_dates.log 2>/dev/null || echo 'No log'"
)
print(stdout.read().decode().strip())

client.close()
