# Audit-based Deletion Forensics for ai-costing-system

> 防御 2026-05-12 那次"53 个文件被外部动作（疑为 Cursor IDE worktree sync）静默删除"事件再次发生。
> 之后任何对 `/home/admin/ai-costing-system/` 树的 unlink/rename，syscall 级别都被 root 守门记录，**取证完整、零打扰**。

---

## 一、装了什么

| 组件 | 文件 | 作用 |
|---|---|---|
| Audit 规则 | `/etc/audit/rules.d/99-costing-files.rules`（源在 `ops/audit/99-costing-files.rules`） | kernel syscall hook：录制 unlink/unlinkat/rename/renameat/renameat2/rmdir 在 `dir=/home/admin/ai-costing-system` 下的所有成功调用，标 key=`costing_del` |
| Audit 日志 | `/var/log/audit/audit.log` | root:root 600，但加了 `setfacl u:admin:r`，admin 无 sudo 可读 |
| Logrotate hook | `/etc/cron.daily/restore-audit-acl` | 防 audit 内部轮转后丢 ACL |
| 查询脚本 | `ops/audit/who-deleted.sh` | 友好查询封装，按时间窗口聚合 SYSCALL+CWD+PATH 三段，输出"谁/何时/在哪/删了什么" |
| 每日汇总 | `ops/audit/daily_summary.sh` + `~/.config/systemd/user/costing-audit-summary.{service,timer}` | 每天 08:00 自动汇总过去 24h，写到 `~/.local/share/costing-audit/summary.log`；24h 内 ≥20 条事件触发 ALERT 文件 |

---

## 二、日常使用（你只需要记这几条）

```bash
# 最常用 - 看最近 24h 谁删了文件
ops/audit/who-deleted.sh

# 看今天
ops/audit/who-deleted.sh today

# 看最近 1 小时（IDE 刚重启完，怀疑刚发生删除时用）
ops/audit/who-deleted.sh 1h

# 看最近 7 天
ops/audit/who-deleted.sh 7d

# 看每日 8 点自动汇总的累计日志
tail -200 ~/.local/share/costing-audit/summary.log

# 看异常报警（24h 内删除超过 20 条文件就生成）
ls -la ~/.local/share/costing-audit/ALERT_*.txt 2>/dev/null
```

每条事件输出格式：

```
[2026-05-12 07:48:28] unlinkat   pid=1375031 ppid=1375031 exe=/usr/bin/rm
    cwd  : /home/admin/ai-costing-system
    target: ops/audit/_audit_test_1375031.tmp
```

字段含义：
- `unlinkat` — 实际 syscall（删文件 / `rmdir` 删目录 / `renameat2` 改名）
- `pid` / `ppid` — 删除者进程及其父进程，结合 `ps` / journalctl 可追到上下文
- `exe` — 删除者的可执行文件绝对路径（`/usr/bin/rm` 是 shell 删，cursor server 删则是 `/home/admin/.cursor-server/bin/.../node`）
- `cwd` — 当时工作目录
- `target` — 被删的文件相对路径

---

## 三、运维命令

```bash
# 看 audit 规则是否还 active
sudo auditctl -l | grep costing

# 重新加载规则（改了 99-costing-files.rules 之后）
sudo install -m 644 ops/audit/99-costing-files.rules /etc/audit/rules.d/
sudo augenrules --load

# 看每日 timer 状态
systemctl --user list-timers costing-audit-summary.timer

# 立刻手动跑一次每日汇总
systemctl --user start costing-audit-summary.service
```

---

## 四、监控覆盖范围

监控的 syscall：
- `unlink`, `unlinkat`：删除单个文件
- `rmdir`：删除空目录
- `rename`, `renameat`, `renameat2`：移动 / 改名（**包含"覆盖式"删除**：被覆盖那一方会以 nametype=DELETE 出现）

**不**包含 truncate/write 等覆盖文件内容的操作——那个不是删除事件，而且会让 audit log 爆炸。

monitor 范围：整个 `/home/admin/ai-costing-system/` 目录树（递归生效，靠 `-F dir=` filter）。

---

## 五、性能影响

- `dir=` filter 在内核层做路径前缀匹配，命中率极低（项目内大部分操作是 read/write，不是 delete/rename）
- audit log 限制 5 × 8MB = 40MB，自动轮转
- 实测 augenrules --load 0.1s，运行时 CPU 不可观测

---

## 六、为什么用 audit 不用 inotify

| 维度 | auditd | inotify (用户态) |
|---|---|---|
| 拿到 pid/ppid/exe | ✅ | ❌ (fanotify 才行，但要 root) |
| 拿到 cwd | ✅ | ❌ |
| 跨 IDE/sshd/systemd 进程 | ✅ | ✅ |
| root 部署一次永久生效 | ✅ | ❌ (每次开机要拉 daemon) |
| 录到 syscall 名 | ✅ | 仅事件类型 |

inotify 抓不到"谁"，audit 是唯一能给真正取证答案的方式。
