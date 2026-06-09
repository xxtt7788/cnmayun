#!/usr/bin/env python3
"""
Upload and run evaluate_data_readiness.py on remote server.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899')

stdin, stdout, stderr = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && .venv/bin/python -u runner/evaluate_data_readiness.py'"
)
out = stdout.read().decode('utf-8', errors='ignore')
err = stderr.read().decode('utf-8', errors='ignore')
print(out)
if err:
    print("ERR:", err)
client.close()
