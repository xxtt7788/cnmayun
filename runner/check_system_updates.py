#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

print("=== System Info ===")
stdin, stdout, stderr = client.exec_command("lsb_release -a 2>/dev/null || cat /etc/os-release | head -5")
print(stdout.read().decode().strip())

print("\n=== Available Security Updates ===")
stdin2, stdout2, stderr2 = client.exec_command(
    "sudo apt list --upgradable 2>/dev/null | grep -i security | head -10 || echo 'No security updates info available'"
)
print(stdout2.read().decode().strip())

print("\n=== Total Upgradable Packages ===")
stdin3, stdout3, stderr3 = client.exec_command(
    "sudo apt list --upgradable 2>/dev/null | wc -l"
)
print(stdout3.read().decode().strip())

print("\n=== Caddy Version ===")
stdin4, stdout4, stderr4 = client.exec_command("caddy version 2>/dev/null || echo 'Caddy version not available'")
print(stdout4.read().decode().strip())

print("\n=== Python Version ===")
stdin5, stdout5, stderr5 = client.exec_command("/opt/china-succession/.venv/bin/python --version")
print(stdout5.read().decode().strip())

client.close()
