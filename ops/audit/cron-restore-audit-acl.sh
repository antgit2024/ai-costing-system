#!/bin/sh
# Re-apply admin read ACL after audit log rotation.
# auditd rotates internally; cron daily catches any drift.
# Deploy with: sudo cp ops/audit/cron-restore-audit-acl.sh /etc/cron.daily/restore-audit-acl
# Then: sudo chmod +x /etc/cron.daily/restore-audit-acl
[ -f /var/log/audit/audit.log ] && /usr/bin/setfacl -m u:admin:r /var/log/audit/audit.log 2>/dev/null
exit 0
