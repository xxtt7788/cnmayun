#!/usr/bin/env python3
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect('103.218.241.171', username='ubuntu', password='Kclyh8899', timeout=60)

# Check running Python processes
print("=== Running Python Processes ===")
stdin, stdout, stderr = client.exec_command(
    "ps aux | grep '.venv/bin/python' | grep -v grep"
)
procs = stdout.read().decode().strip()
print(procs if procs else "No Python processes running")

# Check data status
print("\n=== Data Status ===")
stdin2, stdout2, stderr2 = client.exec_command(
    "echo 'Kclyh8899' | sudo -S bash -c 'cd /opt/china-succession && .venv/bin/python -c \""
    "import os; ENV_PATH = '/etc/china-succession/china-succession.env';"
    "with open(ENV_PATH) as f:"
    "    for line in f:"
    "        line=line.strip();"
    "        if line and not line.startswith('#') and '=' in line:"
    "            key,value=line.split('=',1);"
    "            if key.startswith('export '): key=key[7:];"
    "            os.environ[key]=value.strip().strip(chr(34)).strip(chr(39))"
    ";import sys;sys.path.insert(0,'.');"
    "from app.db import session_scope;"
    "from app.models import Company, RoleTenure;"
    "from sqlalchemy import func, select;"
    "with session_scope() as db:"
    "    active=db.scalar(select(func.count(Company.id)).where(Company.is_active.is_(True)));"
    "    l2=db.scalar(select(func.count(Company.id)).where(Company.is_active.is_(True), Company.industry_l2.isnot(None)));"
    "    prov=db.scalar(select(func.count(Company.id)).where(Company.is_active.is_(True), Company.province.isnot(None)));"
    "    city=db.scalar(select(func.count(Company.id)).where(Company.is_active.is_(True), Company.city.isnot(None)));"
    "    total_t=db.scalar(select(func.count(RoleTenure.id)));"
    "    has_start=db.scalar(select(func.count(RoleTenure.id)).where(RoleTenure.start_date.isnot(None)));"
    "    print(f'Companies: active={active}, industry_l2={l2} ({l2/active*100:.1f}%), province={prov} ({prov/active*100:.1f}%), city={city} ({city/active*100:.1f}%)');"
    "    print(f'Tenures: total={total_t}, has_start_date={has_start} ({has_start/total_t*100:.1f}%)')"
    "\"'"
)
print(stdout2.read().decode().strip())

# Check disk usage
print("\n=== Disk Usage ===")
stdin3, stdout3, stderr3 = client.exec_command("df -h /opt/china-succession")
print(stdout3.read().decode().strip())

client.close()
