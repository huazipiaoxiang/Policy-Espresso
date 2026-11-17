#!/usr/bin/env bash
# Run once as root on the existing ECS, from the directory containing ecs_release.py.
set -eu
test "$(id -u)" = 0
test -f ecs_release.py
test -f /etc/horizon/horizon.env
test -L /opt/policy-espresso/current
test -x /opt/policy-espresso/venv/bin/uvicorn
id horizon-deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/sh horizon-deploy
install -d -m 700 -o horizon-deploy -g horizon-deploy /home/horizon-deploy/.ssh
install -m 755 -o root -g root ecs_release.py /usr/local/sbin/horizon-release
cat > /usr/local/bin/horizon-ci-dispatch <<'EOF'
#!/bin/sh
exec sudo -n /usr/local/sbin/horizon-release
EOF
chmod 755 /usr/local/bin/horizon-ci-dispatch
cat > /etc/sudoers.d/horizon-deploy <<'EOF'
Defaults:horizon-deploy env_keep += "SSH_ORIGINAL_COMMAND"
horizon-deploy ALL=(root) NOPASSWD: /usr/local/sbin/horizon-release
EOF
chmod 440 /etc/sudoers.d/horizon-deploy
visudo -cf /etc/sudoers.d/horizon-deploy
if [ ! -e /opt/policy-espresso/current/.venv ]; then
  ln -s /opt/policy-espresso/venv /opt/policy-espresso/current/.venv
fi
install -d /etc/systemd/system/horizon-api.service.d /etc/systemd/system/horizon-web.service.d
cat > /etc/systemd/system/horizon-api.service.d/release.conf <<'EOF'
[Service]
ExecStartPre=
ExecStart=
ExecStart=/opt/policy-espresso/current/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
EOF
cat > /usr/local/bin/horizon-web-start <<'EOF'
#!/bin/sh
if [ -f /opt/policy-espresso/current/frontend/server.js ]; then
  exec /usr/bin/node /opt/policy-espresso/current/frontend/server.js
fi
exec /usr/bin/node /opt/policy-espresso/current/frontend/node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000
EOF
chmod 755 /usr/local/bin/horizon-web-start
cat > /etc/systemd/system/horizon-web.service.d/release.conf <<'EOF'
[Service]
Environment=HOSTNAME=127.0.0.1
Environment=PORT=3000
ExecStart=
ExecStart=/usr/local/bin/horizon-web-start
EOF
systemctl daemon-reload
echo 'Receiver installed. Add the restricted public key before using it. Running services were not restarted.'
