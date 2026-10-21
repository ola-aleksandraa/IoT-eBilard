set -eu

APP_DIR=/opt/bilard
APP_USER=bilard

[ "$(id -u)" -eq 0 ] || { echo "Please run with sudo."; exit 1; }

if [ ! -d /run/systemd/system ]; then
    if grep -qi microsoft /proc/version; then
        echo "==> systemd is not running in this WSL distro; enabling it"
        if ! grep -Eq '^[[:space:]]*systemd[[:space:]]*=[[:space:]]*true' /etc/wsl.conf 2>/dev/null; then
            if grep -q '^\[boot\]' /etc/wsl.conf 2>/dev/null; then
                sed -i '/^\[boot\]/a systemd=true' /etc/wsl.conf
            else
                printf '\n[boot]\nsystemd=true\n' >> /etc/wsl.conf
            fi
        fi
        echo "Now run in Windows PowerShell:  wsl --shutdown"
        echo "Then reopen Ubuntu and run this script again."
        exit 0
    fi
    echo "systemd is required but not running."
    exit 1
fi

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv mysql-server

echo "==> Setting up MySQL"
systemctl enable --now mysql

DB_PASSWORD=$(tr -dc 'a-f0-9' < /dev/urandom | head -c 32)
mysql <<SQL
CREATE DATABASE IF NOT EXISTS bilard CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'bilard'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER 'bilard'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON bilard.* TO 'bilard'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "==> Installing the application"
id -u "$APP_USER" > /dev/null 2>&1 || \
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/bilard_api"
cp -r bilard_api requirements.txt "$APP_DIR/"
[ -d "$APP_DIR/venv" ] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --no-cache-dir -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Writing service configuration"
mkdir -p /etc/bilard
cat > /etc/bilard/bilard.env <<EOF
DATABASE_URL=mysql+pymysql://bilard:${DB_PASSWORD}@127.0.0.1:3306/bilard
LISTEN_HOST=127.0.0.1
LISTEN_PORT=8000
EOF
chown root:"$APP_USER" /etc/bilard/bilard.env
chmod 640 /etc/bilard/bilard.env

cp deploy/bilard-api.service /etc/systemd/system/bilard-api.service
systemctl daemon-reload
systemctl enable bilard-api
systemctl restart bilard-api

echo "==> Done. Check: systemctl status bilard-api   |   curl http://localhost:8000/states"