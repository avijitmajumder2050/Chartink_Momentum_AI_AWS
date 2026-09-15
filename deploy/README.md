# Staging deployment (AWS, ap-south-1)

One CloudFront distribution fronts both pieces — same origin from the
browser's point of view, so no CORS and no custom domain/ACM cert are
needed. `/api/*` and `/firebase-messaging-sw.js` route to the EC2
backend; everything else routes to the S3-hosted SPA build.

| Resource | Value |
|---|---|
| CloudFront distribution | `E3SG9FAP3WCJBZ` — `https://dz1fb1xrtg7b3.cloudfront.net` |
| Frontend S3 bucket | `quantile-frontend-staging` (private, OAC-only) |
| Backend EC2 instance | `i-035c10ae55c3f8b9c` (t3.micro), security group `sg-073a1f6cc534ed636` |
| EC2 launch template | `quantile-backend-lt` (`lt-0fdfe8cd0e39e71a2`) — documents the instance's exact config; not directly invoked by the daily start/stop, which targets the existing instance |
| EC2 IAM role | `quantile-staging-ec2-role` / instance profile `quantile-staging-ec2-profile` |
| Backend systemd service | `quantile-backend` — `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8000 wsgi:app` |
| Repo URL for EC2 to clone | SSM `/chartink-momentum-ai/github_repo` |
| Scheduler/on-demand Lambda | `quantile-backend-scheduler` (`deploy/lambda/handler.py`) |
| REST API (fronts the Lambda) | `5k5etz73r9` — `https://5k5etz73r9.execute-api.ap-south-1.amazonaws.com/prod/` |
| On-demand toggle page | `https://dz1fb1xrtg7b3.cloudfront.net/ondemand.html` (`deploy/ondemand.html`, standalone, not part of the React app) |
| EventBridge schedules | `quantile-backend-start` (9:00 IST Mon-Fri), `quantile-backend-stop` (11:00 IST Mon-Fri) |
| Trigger-key secret | SSM `/chartink-momentum-ai/scheduler_trigger_key` (SecureString) |

## Scheduled + on-demand start/stop

The backend only runs 9:00-11:00 IST on weekdays (EventBridge
Scheduler, both schedules set with `ScheduleExpressionTimezone:
Asia/Kolkata` so the cron is written directly in IST) — `start` and
`stop` actions on `quantile-backend-scheduler`, which just calls
`StartInstances`/`StopInstances` on the existing instance.

The instance has no Elastic IP, so its public DNS changes on every
stop -> start (standard EC2 behavior) — the Lambda's `start` action
polls until the instance is running with a new `PublicDnsName`, then
updates CloudFront's `ec2-backend` origin to match (`GetDistribution
Config` for the ETag, `UpdateDistribution` with just that one field
changed). **CloudFront then takes 5-15 minutes to propagate** — the
API will 502/504 for a real stretch of each morning's window even
though the instance itself is already up. An Elastic IP would remove
this gap entirely but now costs a small 24/7 fee under AWS's current
public-IPv4 pricing even while stopped — likely not worth it for a
2-hour/day window, but worth reconsidering if the gap becomes annoying.

The same Lambda is reachable on demand from `deploy/ondemand.html` — a
plain HTML/JS page (no build step, no React) deployed to the *same* S3
bucket as the main app but not linked from it, calling the REST API
directly with a shared-secret header. That secret is **not real
security** (it's necessarily visible in the page's own JS source to
anyone who opens it) — it only stops an accidental/drive-by trigger of
billable infrastructure.

**Why a REST API and not an HTTP API or a Function URL:** both of
those were tried first and failed in ways never fully root-caused —
a Function URL with `AuthType: NONE` returned 403 from the URL layer
itself no matter how long we waited after adding the public-invoke
resource policy (the exact documented policy shape), and an HTTP API
quick-created from `--target` returned 500 with zero Lambda
invocations ever reaching CloudWatch Logs, even after fixing the
`apigateway.amazonaws.com` invoke permission's source ARN. A plain
REST API (`apigatewayv2`'s older sibling) with an explicit `ANY`
method + `AWS_PROXY` integration + a manually added invoke permission
worked immediately. If revisiting this, that's the known-good path.

**Redeploying the Lambda after editing `deploy/lambda/handler.py`:**
```
cd deploy/lambda
zip -r ../lambda_function.zip handler.py
aws lambda update-function-code --function-name quantile-backend-scheduler --zip-file fileb://../lambda_function.zip --region ap-south-1
```

**Redeploying `ondemand.html`:** the committed copy has `__TRIGGER_KEY__`
as a placeholder (the real secret is never committed) — substitute it
with the value from SSM `/chartink-momentum-ai/scheduler_trigger_key`
before uploading:
```
aws s3 cp ondemand.html s3://quantile-frontend-staging/ondemand.html --content-type text/html --region ap-south-1
# (after substituting the real key in place of __TRIGGER_KEY__ in a local copy)
```

## Redeploying the backend (after a `git push`)

SSH in (EC2 Instance Connect works even with no local key — see below)
and:
```
cd /home/ec2-user/Chartink_Momentum_AI_AWS
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart quantile-backend
```

## Redeploying the frontend

```
cd frontend
npm run build   # picks up .env.production automatically
aws s3 sync dist/ s3://quantile-frontend-staging/ --delete --region ap-south-1
aws cloudfront create-invalidation --distribution-id E3SG9FAP3WCJBZ --paths "/*"
```

## SSH access without a local key file

The `myapp_aws2` key pair this instance was launched with isn't
available as a usable OpenSSH key on this machine. Use EC2 Instance
Connect instead (needs `ec2-instance-connect:SendSSHPublicKey` IAM
permission, and the security group's SSH rule to include your current
IP — it's currently restricted to one specific IP, update it if
you're connecting from elsewhere):
```
ssh-keygen -t ed25519 -f /tmp/eic_key -N ""
aws ec2-instance-connect send-ssh-public-key \
  --instance-id i-035c10ae55c3f8b9c --instance-os-user ec2-user \
  --ssh-public-key file:///tmp/eic_key.pub \
  --availability-zone ap-south-1a --region ap-south-1
ssh -i /tmp/eic_key ec2-user@<current-public-dns>
```
The pushed key is only valid ~60 seconds, so send it immediately
before connecting. The instance's public DNS changes on every
stop/start (see "Scheduled + on-demand start/stop" below) — get the
current one with `aws ec2 describe-instances --instance-ids
i-035c10ae55c3f8b9c --query "Reservations[0].Instances[0].PublicDnsName"`
or from the `quantile-backend-scheduler` Lambda's own `status` action.

## Recreating the EC2 instance from scratch

`ec2-userdata.sh` in this directory is what was actually used (as
`--user-data fileb://deploy/ec2-userdata.sh` — binary mode; the AWS
CLI's text-decode path failed on this file for reasons never fully
pinned down, `fileb://` sidesteps it). It bakes in `AWS_DEFAULT_REGION`
for the systemd service, which the first deploy initially missed —
connectors/secrets.py and friends fall back to that env var when no
explicit region is passed, and an instance role carries no region
info the way a local `AWS_PROFILE` does.

## Known gaps / next steps

- No custom domain — `*.cloudfront.net` only, per current preference.
- `PriceClass_100` on the CloudFront distribution (US/Europe edges
  only) was chosen to minimize cost for staging. Reconsider
  `PriceClass_200` or `PriceClass_All` before pointing real Indian
  users at this, for better edge latency.
- Single `t3.micro`, single gunicorn worker — fine for staging; the
  alert-monitor bot (`wsgi.py`) specifically depends on staying at one
  worker, so scaling this up needs a real design change, not just a
  flag flip.
- No CI/CD — both the frontend and backend "redeploy" steps above are
  manual.
