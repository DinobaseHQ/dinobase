#!/usr/bin/env bash
# One-shot provisioning for a fresh Hetzner Cloud VM (Ubuntu 24.04 LTS).
#
# Usage (on a fresh VM, as root):
#   curl -fsSL https://raw.githubusercontent.com/DinobaseHQ/dinobase/main/ee/cloud/deploy/hetzner/install.sh | bash
#   cd /opt/dinobase/ee/cloud/deploy/hetzner
#   cp .env.example .env && $EDITOR .env
#   docker compose up -d --build
#
# What this script does:
#   - Installs Docker Engine + the compose plugin
#   - Clones the Dinobase repo into /opt/dinobase
#   - Opens UFW for 22/80/443
#   - Leaves you at the deploy dir with .env.example ready to copy

set -euo pipefail

REPO_URL="${DINOBASE_REPO_URL:-https://github.com/DinobaseHQ/dinobase.git}"
REPO_REF="${DINOBASE_REPO_REF:-main}"
INSTALL_DIR="${DINOBASE_INSTALL_DIR:-/opt/dinobase}"

if [ "$(id -u)" -ne 0 ]; then
	echo "Run as root (or with sudo)." >&2
	exit 1
fi

echo "==> Updating apt"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl git gnupg ufw

echo "==> Installing Docker Engine"
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
		| gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	chmod a+r /etc/apt/keyrings/docker.gpg
fi
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
	> /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

echo "==> Configuring UFW (22/tcp, 80/tcp, 443/tcp)"
ufw allow OpenSSH || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
yes | ufw enable || true

echo "==> Cloning ${REPO_URL}@${REPO_REF} -> ${INSTALL_DIR}"
if [ -d "${INSTALL_DIR}/.git" ]; then
	git -C "${INSTALL_DIR}" fetch --all
	git -C "${INSTALL_DIR}" checkout "${REPO_REF}"
	git -C "${INSTALL_DIR}" pull --ff-only
else
	git clone --branch "${REPO_REF}" "${REPO_URL}" "${INSTALL_DIR}"
fi

DEPLOY_DIR="${INSTALL_DIR}/ee/cloud/deploy/hetzner"
cd "${DEPLOY_DIR}"

cat <<EOF

==> Done.

Next steps:

  cd ${DEPLOY_DIR}
  cp .env.example .env
  \$EDITOR .env              # fill in domains, Supabase keys, encryption key
  docker compose up -d --build

Then point these DNS records at this VM's public IP:
  A   \$DINOBASE_WEB_DOMAIN  -> <this VM IP>
  A   \$DINOBASE_API_DOMAIN  -> <this VM IP>

Caddy will auto-issue Let's Encrypt certs on first request.
EOF
