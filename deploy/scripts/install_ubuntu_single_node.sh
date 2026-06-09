#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-china-succession}"
APP_DIR="${APP_DIR:-/opt/china-succession}"
ENV_DIR="${ENV_DIR:-/etc/china-succession}"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 执行：sudo bash deploy/scripts/install_ubuntu_single_node.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip postgresql postgresql-client caddy rsync curl software-properties-common

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update
  apt-get install -y python3.11 python3.11-venv python3.11-distutils
  PYTHON_BIN="python3.11"
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR" "$ENV_DIR" /var/backups/china-succession
rsync -a --delete \
  --exclude '.venv' \
  --exclude 'data/*.db' \
  --exclude 'data/*.zip' \
  --exclude 'runner' \
  --exclude '.gstack' \
  --exclude 'china_succession.egg-info' \
  ./ "$APP_DIR"/

"$PYTHON_BIN" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -e "$APP_DIR"
chmod +x "$APP_DIR"/deploy/scripts/*.sh

if [ ! -f "$ENV_DIR/china-succession.env" ]; then
  cp "$APP_DIR/.env.production.example" "$ENV_DIR/china-succession.env"
  chmod 600 "$ENV_DIR/china-succession.env"
  echo "已生成 $ENV_DIR/china-succession.env，请先填写真实生产配置后再启动服务。"
fi

cp "$APP_DIR"/deploy/systemd/*.service /etc/systemd/system/
cp "$APP_DIR"/deploy/systemd/*.timer /etc/systemd/system/
chown -R "$APP_USER:$APP_USER" "$APP_DIR" /var/backups/china-succession

systemctl daemon-reload
systemctl enable china-succession-web.service
systemctl enable china-succession-notices.timer
systemctl enable china-succession-zero-repair.timer
systemctl enable china-succession-backup.timer

echo "安装完成。下一步：填写 $ENV_DIR/china-succession.env，然后执行："
echo "systemctl start china-succession-web.service"
echo "systemctl start china-succession-notices.timer china-succession-zero-repair.timer china-succession-backup.timer"
