#!/usr/bin/env python3
"""
Upload and run debug_cninfo_intro2.py on remote server.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899')

sftp = client.open_sftp()
sftp.put('runner/debug_cninfo_intro2.py', '/tmp/debug_cninfo_intro2.py')
sftp.close()

stdin, stdout, stderr = client.exec_command(
    "echo 'Kclyh8899' | sudo -S cp /tmp/debug_cninfo_intro2.py /opt/china-succession/runner/debug_cninfo_intro2.py && "
    "sudo -S chown china-succession:china-succession /opt/china-succession/runner/debug_cninfo_intro2.py"
)

stdin2, stdout2, stderr2 = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && .venv/bin/python -u runner/debug_cninfo_intro2.py'"
)
out = stdout2.read().decode('utf-8', errors='ignore')
err = stderr2.read().decode('utf-8', errors='ignore')
print(out)
if err:
    print("ERR:", err)
client.close()
