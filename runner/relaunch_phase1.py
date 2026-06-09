#!/usr/bin/env python3
"""
Re-launch Phase 1 (person profile enrichment) with fixed script.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899')

sftp = client.open_sftp()
sftp.put('runner/batch_enrich_person_profiles.py', '/tmp/batch_enrich_person_profiles.py')
sftp.close()

stdin, stdout, stderr = client.exec_command(
    "echo 'Kclyh8899' | sudo -S cp /tmp/batch_enrich_person_profiles.py /opt/china-succession/runner/batch_enrich_person_profiles.py && "
    "sudo -S chown china-succession:china-succession /opt/china-succession/runner/batch_enrich_person_profiles.py"
)

stdin2, stdout2, stderr2 = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && nohup .venv/bin/python -u runner/batch_enrich_person_profiles.py > runner/enrich_profiles.log 2>&1 & echo $!'"
)
pid = stdout2.read().decode().strip()
print(f"PID: {pid}")
client.close()
