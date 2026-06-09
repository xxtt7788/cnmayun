#!/usr/bin/env python3
"""
Deploy runner script to server and execute via SSH.
Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
from paramiko import SSHClient, AutoAddPolicy
import sys

def deploy_and_run(local_path, remote_name, use_nohup=True):
    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy())
    client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899')
    
    sftp = client.open_sftp()
    sftp.put(local_path, f'/tmp/{remote_name}')
    sftp.close()
    
    # copy to target
    cmd1 = (
        f"echo 'Kclyh8899' | sudo -S cp /tmp/{remote_name} /opt/china-succession/runner/{remote_name} && "
        f"sudo -S chown china-succession:china-succession /opt/china-succession/runner/{remote_name}"
    )
    stdin, stdout, stderr = client.exec_command(cmd1)
    stdout.channel.recv_exit_status()
    
    if use_nohup:
        cmd2 = (
            f"echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && nohup .venv/bin/python -u runner/{remote_name} > runner/{remote_name.replace(\".py\", \".log\")} 2>&1 & echo $!'"
        )
        stdin2, stdout2, stderr2 = client.exec_command(cmd2)
        pid = stdout2.read().decode().strip()
        print(f"Deployed {remote_name}, PID: {pid}")
    else:
        cmd2 = (
            f"echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && .venv/bin/python -u runner/{remote_name}'"
        )
        stdin2, stdout2, stderr2 = client.exec_command(cmd2)
        out = stdout2.read().decode()
        err = stderr2.read().decode()
        print(f"Output:\n{out}")
        if err:
            print(f"Stderr:\n{err}")
    
    client.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python deploy_and_run.py <local_path> <remote_name> [nohup]")
        sys.exit(1)
    deploy_and_run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else True)
