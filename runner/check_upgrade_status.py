#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

# Check if apt is still running
stdin, stdout, stderr = client.exec_command("ps aux | grep apt | grep -v grep")
apt_procs = stdout.read().decode().strip()
if apt_procs:
    print("Apt processes still running:")
    print(apt_procs)
else:
    print("No apt processes running")

# Check reboot status
print("\n=== Reboot Status ===")
stdin2, stdout2, stderr2 = client.exec_command("[ -f /var/run/reboot-required ] && echo 'REBOOT REQUIRED' || echo 'No reboot needed'")
print(stdout2.read().decode().strip())

# Check remaining upgradable packages
print("\n=== Remaining Upgradable ===")
stdin3, stdout3, stderr3 = client.exec_command("sudo apt list --upgradable 2>/dev/null | wc -l")
print(f"Upgradable packages: {stdout3.read().decode().strip()}")

# Check disk usage after cleanup
print("\n=== Disk Usage ===")
stdin4, stdout4, stderr4 = client.exec_command("df -h / | tail -1")
print(stdout4.read().decode().strip())

client.close()
