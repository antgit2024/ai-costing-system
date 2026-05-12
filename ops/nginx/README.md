# Nginx config backup for ai-costing.com (a.k.a. work.znma.com costing)

`ai-costing.conf` is the **production nginx site config** for the costing
frontend + backend reverse proxy. This directory holds a **git-tracked
backup** of that file — the live copy is at `/etc/nginx/conf.d/ai-costing.conf`
(owned by root).

## Why a backup, not a symlink?

Nginx in `/etc/nginx/conf.d/` requires real files (root-owned). symlink to
home dir would be flaky (SELinux, `nginx -t`, root readability). So we keep
a git copy and re-deploy on demand.

## Deploy / restore

```bash
# Verify the local backup matches production
sudo diff -u ops/nginx/ai-costing.conf /etc/nginx/conf.d/ai-costing.conf

# If production was wiped or you want git → production
sudo cp ops/nginx/ai-costing.conf /etc/nginx/conf.d/ai-costing.conf
sudo nginx -t                  # syntax check
sudo systemctl reload nginx    # zero-downtime reload

# After editing the production copy by hand (e.g. emergency hotfix), bring git in sync
sudo cp /etc/nginx/conf.d/ai-costing.conf ops/nginx/ai-costing.conf
git diff ops/nginx/ai-costing.conf      # review
git add ops/nginx/ && git commit -m "ops(nginx): sync ai-costing.conf"
```

## What's in this config

- `server_name 47.99.89.206` (legacy IP entry; production also reachable via work.znma.com)
- `root /var/www/html/ai-costing/dist` — frontend SPA build output
- `proxy_pass http://127.0.0.1:8800/api/planner/` — reverse proxy to planner-costing.service
- Cache-Control: no-cache for client-side hot reloads of the SPA bundle
