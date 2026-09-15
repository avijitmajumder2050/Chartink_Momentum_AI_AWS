#!/bin/bash
# EC2 user-data for the staging backend (t3.micro, Amazon Linux 2023).
# See deploy/README.md for the full picture (CloudFront + S3 + this
# instance). Re-run by relaunching an instance with this as --user-data
# (fileb://, not file:// — the AWS CLI's user-data text-decode path has
# choked on this file before; binary mode sidesteps it).
set -e

LOG=/var/log/quantile-bootstrap.log
exec > >(tee -a "$LOG") 2>&1

echo "🚀 Bootstrapping Quantile staging backend"

REGION="ap-south-1"
SSM_REPO_PARAM="/chartink-momentum-ai/github_repo"
APP_USER="ec2-user"
APP_HOME="/home/ec2-user"

# ------------------------------------------------------
# System update & deps
# ------------------------------------------------------
sudo yum update -y
sudo timedatectl set-timezone Asia/Kolkata
sudo yum install -y git python3.11 python3.11-pip python3.11-devel awscli
echo "✅ Installed Python 3.11"

# ------------------------------------------------------
# Chromium runtime deps for Playwright (Amazon Linux is not
# officially supported by `playwright install --with-deps`, so
# install the standard headless-chromium dependency set directly
# rather than relying on that to work).
# ------------------------------------------------------
sudo yum install -y nss atk cups-libs libdrm libxkbcommon \
  at-spi2-atk libXcomposite libXdamage libXrandr mesa-libgbm \
  alsa-lib pango libxshmfence || echo "⚠️ some chromium deps failed to install — continuing"

# ------------------------------------------------------
# Get repo URL from SSM, clone (idempotent)
# ------------------------------------------------------
REPO_URL=$(aws ssm get-parameter --name "$SSM_REPO_PARAM" --region "$REGION" --query "Parameter.Value" --output text)
cd "$APP_HOME"
REPO_NAME=$(basename "$REPO_URL" .git)
if [ ! -d "$REPO_NAME" ]; then
  git clone "$REPO_URL"
fi
cd "$REPO_NAME"

# ------------------------------------------------------
# Python venv (3.11) + deps
# ------------------------------------------------------
if [ ! -d "venv" ]; then
  /usr/bin/python3.11 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Installed Python requirements"

playwright install chromium || echo "⚠️ playwright chromium download failed — scraping-dependent features will degrade gracefully"

mkdir -p .cache
sudo chown -R $APP_USER:$APP_USER "$APP_HOME/$REPO_NAME"

# playwright install (above) runs as root — user-data scripts execute
# as root end to end — so the browser lands in /root/.cache/ms-playwright,
# not $APP_HOME/.cache. The systemd service below runs as $APP_USER and
# looks in *its* home dir, finds nothing there, and every IPO/fundamentals
# scrape that needs a real browser fails with "Executable doesn't exist".
# Learned this the hard way on the first deploy — copy the browser cache
# to where the service will actually look for it.
if [ -d /root/.cache/ms-playwright ]; then
  sudo mkdir -p "$APP_HOME/.cache"
  sudo cp -r /root/.cache/ms-playwright "$APP_HOME/.cache/"
  sudo chown -R $APP_USER:$APP_USER "$APP_HOME/.cache"
fi

# ------------------------------------------------------
# systemd service — single gunicorn worker (see wsgi.py's own
# comment: more than one worker double-starts the alert-monitor bot).
#
# AWS_DEFAULT_REGION is required: connectors/secrets.py and several
# connectors fall back to this env var when no explicit region is
# passed, and an EC2 instance role carries no region info the way a
# local `AWS_PROFILE` config does — omitting this makes every boto3
# client construction raise NoRegionError at first request. Learned
# this the hard way on the first deploy; don't drop it on a future one.
# ------------------------------------------------------
sudo tee /etc/systemd/system/quantile-backend.service > /dev/null <<EOF
[Unit]
Description=Quantile (Chartink Momentum AI) staging backend
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_HOME/$REPO_NAME
Environment=PYTHONUNBUFFERED=1
Environment=AWS_DEFAULT_REGION=$REGION
ExecStart=$APP_HOME/$REPO_NAME/venv/bin/gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8000 --access-logfile - --error-logfile - wsgi:app
Restart=always
RestartSec=10
StandardOutput=append:/var/log/quantile-backend.log
StandardError=append:/var/log/quantile-backend.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable quantile-backend
sudo systemctl restart quantile-backend

echo "✅ Quantile backend started; logs at /var/log/quantile-backend.log"
