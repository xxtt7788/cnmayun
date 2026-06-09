#!/usr/bin/env python3
"""
Upload and run verify_profiles.py on remote server.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899')

sftp = client.open_sftp()
sftp.put('runner/verify_profiles.py', '/tmp/verify_profiles.py')
sftp.close()

stdin, stdout, stderr = client.exec_command(
    "echo 'Kclyh8899' | sudo -S cp /tmp/verify_profiles.py /opt/china-succession/runner/verify_profiles.py && "
    "sudo -S chown china-succession:china-succession /opt/china-succession/runner/verify_profiles.py"
)

stdin2, stdout2, stderr2 = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && .venv/bin/python -u runner/verify_profiles.py'"
)
out = stdout2.read().decode('utf-8', errors='ignore')
err = stderr2.read().decode('utf-8', errors='ignore')
print(out)
if err:
    print("ERR:", err)
client.close()
