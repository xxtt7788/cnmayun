#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

print("=== Listening Ports ===")
stdin, stdout, stderr = client.exec_command("sudo ss -tlnp | grep -E ':(22|80|443|8000|5432)'")
print(stdout.read().decode().strip())

print("\n=== UFW Status ===")
stdin2, stdout2, stderr2 = client.exec_command("sudo ufw status 2>/dev/null || echo 'UFW not installed/active'")
print(stdout2.read().decode().strip())

print("\n=== Caddy Status ===")
stdin3, stdout3, stderr3 = client.exec_command("sudo systemctl status caddy --no-pager 2>/dev/null | head -5 || echo 'Caddy not running'")
print(stdout3.read().decode().strip())

client.close()
