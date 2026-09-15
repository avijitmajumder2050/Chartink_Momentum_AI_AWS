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
| EC2 IAM role | `quantile-staging-ec2-role` / instance profile `quantile-staging-ec2-profile` |
| Backend systemd service | `quantile-backend` — `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8000 wsgi:app` |
| Repo URL for EC2 to clone | SSM `/chartink-momentum-ai/github_repo` |

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
ssh -i /tmp/eic_key ec2-user@ec2-3-6-39-229.ap-south-1.compute.amazonaws.com
```
The pushed key is only valid ~60 seconds, so send it immediately
before connecting.

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
