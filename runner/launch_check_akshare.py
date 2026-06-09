#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

sftp = client.open_sftp()
sftp.put('runner/_check_akshare.py', '/tmp/_check_akshare.py')
sftp.close()

stdin, stdout, stderr = client.exec_command(
    "echo 'Kclyh8899' | sudo -S cp /tmp/_check_akshare.py /opt/china-succession/runner/_check_akshare.py"
)

stdin2, stdout2, stderr2 = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && timeout 120 .venv/bin/python runner/_check_akshare.py'"
)
print(stdout2.read().decode().strip())
err = stderr2.read().decode().strip()
if err:
    print("ERR:", err)
client.close()
