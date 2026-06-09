#!/usr/bin/env python3
"""
Apply security updates to the server.
Author: Kimi Code CLI Agent
"""
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

print("=== Updating package list ===")
stdin, stdout, stderr = client.exec_command("echo 'Kclyh8899' | sudo -S apt update -qq")
print(stdout.read().decode().strip()[-500:] if len(stdout.read().decode()) > 500 else stdout.read().decode().strip())
err = stderr.read().decode().strip()
if err:
    print(f"STDERR: {err[-500:]}")

print("\n=== Upgrading packages (unattended) ===")
# Use DEBIAN_FRONTEND=noninteractive to avoid prompts
stdin2, stdout2, stderr2 = client.exec_command(
    "echo 'Kclyh8899' | sudo -S DEBIAN_FRONTEND=noninteractive apt upgrade -y -qq"
)
out = stdout2.read().decode().strip()
print(out[-1000:] if len(out) > 1000 else out)
err2 = stderr2.read().decode().strip()
if err2:
    print(f"STDERR: {err2[-500:]}")

print("\n=== Cleaning up ===")
stdin3, stdout3, stderr3 = client.exec_command("echo 'Kclyh8899' | sudo -S apt autoremove -y -qq")
print(stdout3.read().decode().strip()[-500:] if len(stdout3.read().decode()) > 500 else stdout3.read().decode().strip())

print("\n=== Checking if reboot required ===")
stdin4, stdout4, stderr4 = client.exec_command("[ -f /var/run/reboot-required ] && echo 'REBOOT REQUIRED' || echo 'No reboot needed'")
reboot_status = stdout4.read().decode().strip()
print(reboot_status)

client.close()
print("\nDone.")
