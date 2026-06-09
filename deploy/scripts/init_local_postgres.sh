#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-china_succession}"
DB_USER="${DB_USER:-china_succession}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"

if [[ ! "$DB_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "DB_NAME 只能包含字母、数字、下划线，且不能以数字开头"
  exit 1
fi

if [[ ! "$DB_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "DB_USER 只能包含字母、数字、下划线，且不能以数字开头"
  exit 1
fi

escaped_password="${DB_PASSWORD//\'/\'\'}"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 执行：sudo DB_PASSWORD='强密码' bash deploy/scripts/init_local_postgres.sh"
  exit 1
fi

systemctl enable --now postgresql

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE "${DB_USER}" LOGIN PASSWORD '${escaped_password}';
  ELSE
    ALTER ROLE "${DB_USER}" WITH PASSWORD '${escaped_password}';
  END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi

echo "PostgreSQL 初始化完成"
echo "DATABASE_URL=postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}"
