#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())

try:
    client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=30)
    print("SSH connection restored")
    
    # Check uptime
    stdin, stdout, stderr = client.exec_command("uptime")
    print(f"Uptime: {stdout.read().decode().strip()}")
    
    # Check services
    print("\n=== Services ===")
    stdin2, stdout2, stderr2 = client.exec_command("ps aux | grep -E 'uvicorn|caddy' | grep -v grep | awk '{print $11, $2}'")
    procs = stdout2.read().decode().strip()
    if procs:
        print(procs)
    else:
        print("WARNING: No uvicorn/caddy found")
    
    # Check health endpoint
    print("\n=== Health Check ===")
    stdin3, stdout3, stderr3 = client.exec_command("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz")
    code = stdout3.read().decode().strip()
    print(f"HTTP {code}")
    
    # Check remaining upgradable packages
    print("\n=== Remaining Upgrades ===")
    stdin4, stdout4, stderr4 = client.exec_command("sudo apt list --upgradable 2>/dev/null | wc -l")
    print(f"Upgradable: {stdout4.read().decode().strip()}")
    
    client.close()
    print("\nServer is back online.")
except Exception as e:
    print(f"Server not yet reachable: {e}")
