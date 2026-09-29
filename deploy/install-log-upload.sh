#!/bin/bash
# Ship the backend's log to S3, one file per day — same convention as
# trading-bot-algo and the other apps under s3://new-dhan-trading-data/
# trading-bot/logs/ (one object per app, overwritten in place; the
# delete-trading-bot-logs Lambda clears the prefix at 23:45 IST).
#
#   s3://new-dhan-trading-data/trading-bot/logs/quantile-backend.log
#
# - Uploaded every 5 minutes (systemd timer) and when the service stops.
# - Holds only the current IST date, nothing older anywhere: on the
#   first run of a new day the local /var/log/quantile-backend.log is
#   emptied in place (no previous-day copy is kept — smallest possible
#   file; the service writes with O_APPEND, so it just continues at the
#   new end). That runs as ExecStartPre too, so a 09:00 start — the
#   instance is normally off at midnight — begins the day's file before
#   the app writes its first line.
#
# Idempotent; run as root. Called from ec2-userdata.sh, and can be
# re-run by hand on an existing instance:
#   sudo bash deploy/install-log-upload.sh
set -euo pipefail

S3_DEST="s3://new-dhan-trading-data/trading-bot/logs/quantile-backend.log"

cat > /usr/local/bin/upload-quantile-backend-log.sh <<EOF
#!/bin/bash
# Installed by deploy/install-log-upload.sh — see there.
set -u
LOG=/var/log/quantile-backend.log
MARK=/var/log/quantile-backend.log.date
TODAY=\$(TZ=Asia/Kolkata date +%F)
touch "\$LOG"
if [ "\$(cat "\$MARK" 2>/dev/null)" != "\$TODAY" ]; then
  # New day: start today's file empty — no previous-day copy kept.
  : > "\$LOG"
  rm -f "\$LOG.prev"
  echo "\$TODAY" > "\$MARK"
fi
aws s3 cp "\$LOG" "$S3_DEST" --only-show-errors --content-type "text/plain; charset=utf-8" \\
  || echo "\$(date '+%F %T') log upload to S3 failed" >&2
EOF
chmod 755 /usr/local/bin/upload-quantile-backend-log.sh

cat > /etc/systemd/system/quantile-backend-log-upload.service <<'EOF'
[Unit]
Description=Upload today's quantile-backend.log to S3

[Service]
Type=oneshot
ExecStart=/usr/local/bin/upload-quantile-backend-log.sh
EOF

cat > /etc/systemd/system/quantile-backend-log-upload.timer <<'EOF'
[Unit]
Description=Upload quantile-backend.log to S3 every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

# Hook into the backend service itself: day rollover before it starts,
# final upload after it stops. "+" = run as root (the service runs as
# ec2-user, but the log file is root-owned).
mkdir -p /etc/systemd/system/quantile-backend.service.d
cat > /etc/systemd/system/quantile-backend.service.d/log-upload.conf <<'EOF'
[Service]
ExecStartPre=+/usr/local/bin/upload-quantile-backend-log.sh
ExecStopPost=+/usr/local/bin/upload-quantile-backend-log.sh
EOF

systemctl daemon-reload
systemctl enable --now quantile-backend-log-upload.timer
echo "✅ quantile-backend.log -> $S3_DEST (every 5 min, daily reset)"
