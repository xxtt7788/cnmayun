#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

stdin, stdout, stderr = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession/runner && rm -f _test_*.log backfill_company_location.log backfill_company_location_v*.log backfill_location_batch.log backfill_location_direct.log backfill_location_safe.log'"
)

stdin2, stdout2, stderr2 = client.exec_command(
    "ls -lh /opt/china-succession/runner/*.log 2>/dev/null | awk '{print $5, $9}' || echo 'No log files'"
)
print("Remaining log files:")
print(stdout2.read().decode().strip())

client.close()
