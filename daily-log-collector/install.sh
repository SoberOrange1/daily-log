#!/usr/bin/env bash
#
# daily-log-collector 安装脚本(原生 Mac/Linux)。
#
# 作用:在开发者机器上用"任意一个 Python 3.10+"建一个专属 venv,把 mcp 钉死装进去,
#      部署 server 文件到 Quick 的 mcp-servers 目录,并打印现成的注册配置。
#      不污染开发者已有的 Python 环境,也不依赖 miniconda。
#
# 用法:  bash install.sh
#        DAILY_LOG_SERVER_DIR=/自定义/路径 bash install.sh   # 可覆盖部署位置
#
set -euo pipefail

MCP_VERSION="1.29.0"                        # 与 server.py 的 API 对齐,勿随意升级(2.x 不兼容)
MIN_PY="3.10"                               # mcp 与 server.py 的最低 Python 版本
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="${DAILY_LOG_SERVER_DIR:-$HOME/.quickwork/mcp-servers/daily-log-collector}"
VENV="$SERVER_DIR/.venv"
# 历史/运行时数据目录:独立于代码部署目录,重装代码不动历史。
DATA_DIR="${DAILY_LOG_DATA_DIR:-$HOME/.daily-log-collector}"

say()  { printf '%s\n' "$*"; }
die()  { printf '❌ %s\n' "$*" >&2; exit 1; }

# ---------- 1) 检测一个真正可用的 Python 3.10+ ----------
# 逐个尝试候选,必须能真正执行(xcode 桩会在这一步失败)且版本 >= MIN_PY。
find_python() {
  local candidates=() c bin
  for v in 3.13 3.12 3.11 3.10; do candidates+=("python$v"); done
  candidates+=("python3" "python")
  for p in "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3" \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           "$HOME/.pyenv/shims/python3" /usr/bin/python3; do
    candidates+=("$p")
  done
  for c in "${candidates[@]}"; do
    bin="$(command -v "$c" 2>/dev/null || true)"
    [ -z "$bin" ] && { [ -x "$c" ] && bin="$c" || continue; }
    if "$bin" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= tuple(map(int,'${MIN_PY}'.split('.'))) else 1)" >/dev/null 2>&1; then
      printf '%s\n' "$bin"; return 0
    fi
  done
  return 1
}

PYTHON="$(find_python || true)"
[ -z "$PYTHON" ] && die "没找到可用的 Python ${MIN_PY}+。请先安装(brew install python / pyenv / miniconda)后重跑。"
say "✓ Python: $PYTHON ($("$PYTHON" -V 2>&1))"

# ---------- 2) 探测 git(供 server 采集 commit;不装,只报告)----------
GIT_BIN="$(command -v git 2>/dev/null || true)"
GIT_DIR=""
if [ -n "$GIT_BIN" ] && "$GIT_BIN" --version >/dev/null 2>&1; then
  GIT_DIR="$(cd "$(dirname "$GIT_BIN")" && pwd)"
  say "✓ git: $GIT_BIN ($("$GIT_BIN" --version 2>&1))"
else
  say "⚠ 没探测到可用的 git(macOS 的 /usr/bin/git 可能只是 Xcode 桩)。commit 采集会为空但不报错;装真 git 后重跑即可。"
fi

# ---------- 3) 部署 server 文件 + 安置历史数据 ----------
mkdir -p "$SERVER_DIR" "$DATA_DIR"
for f in server.py merge_history.py render_dashboard.py; do
  [ -f "$SRC_DIR/$f" ] && cp "$SRC_DIR/$f" "$SERVER_DIR/$f"
done
# 迁移:旧版把历史放在部署目录内 data/;若旧位置有、新位置还没有,就搬到独立数据目录。
OLD_HIST="$SERVER_DIR/data/history.json"
NEW_HIST="$DATA_DIR/history.json"
if [ -f "$OLD_HIST" ] && [ ! -f "$NEW_HIST" ]; then
  cp "$OLD_HIST" "$NEW_HIST"
  say "↪ 已迁移历史: $OLD_HIST → $NEW_HIST"
fi
# 只在新位置不存在时初始化,绝不覆盖已有历史
[ -f "$NEW_HIST" ] || printf '{\n  "version": 1,\n  "updated_at": null,\n  "entries": {},\n  "goals": {}\n}\n' > "$NEW_HIST"
say "✓ 代码 → $SERVER_DIR"
say "✓ 历史 → $DATA_DIR"

# ---------- 4) 建 venv + 装 pinned mcp ----------
if [ ! -x "$VENV/bin/python" ]; then
  say "→ 创建 venv: $VENV"
  "$PYTHON" -m venv "$VENV"
fi
say "→ 安装 mcp==$MCP_VERSION 及依赖(隔离在 venv 内)"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet "mcp==$MCP_VERSION"
"$VENV/bin/python" -c "from mcp.server import Server; from mcp.server.stdio import stdio_server; from mcp.types import Tool; print('✓ mcp import 自检通过')"

# ---------- 5) 组装并【自检】env.PATH ----------
# env.PATH 让 server 内的 shutil.which('git') 命中真 git:venv/bin + 探测到的 git 目录 + 常见目录。
# 把 GIT_DIR 排在 /usr/bin 前面,确保真 git 优先于 /usr/bin/git(macOS 上可能是 Xcode 桩)。
PATH_ENV="$VENV/bin"
[ -n "$GIT_DIR" ] && PATH_ENV="$PATH_ENV:$GIT_DIR"
PATH_ENV="$PATH_ENV:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# 关键:用即将写进配置的这份 PATH_ENV,以干净环境复现 server 运行时,
# 检查 shutil.which('git') 到底命中什么、能否真正执行(桩会在 --version 处失败)。
say "→ 自检 env.PATH 下的 git 解析(复现 server 运行时)"
if env -i PATH="$PATH_ENV" HOME="$HOME" "$VENV/bin/python" - <<'PY'
import shutil, subprocess, sys
g = shutil.which("git")
if not g:
    print("   ✗ 这份 PATH 上找不到 git —— commit 采集会为空(server 仍能跑)"); sys.exit(1)
try:
    r = subprocess.run([g, "--version"], capture_output=True, text=True, timeout=10)
except Exception as e:
    print(f"   ✗ {g} 无法执行({e})"); sys.exit(1)
if r.returncode != 0:
    print(f"   ✗ {g} 运行失败(疑似 Xcode 桩):{(r.stderr or '').strip()[:80]}"); sys.exit(1)
print(f"   ✓ git 解析为 {g} -> {r.stdout.strip()}")
PY
then :; else
  say "   ⚠ git 自检未通过:server 能启动,但 git commit 采集会为空。装好真 git(brew install git)后重跑本脚本即可修正 PATH。"
fi

# 自检 Claude/Kiro 会话目录可见性:这两个路径写死在 server.py 里、基于 HOME 展开
# (~/.claude/projects、~/.kiro/sessions),不走 PATH。这里复现 server 的 HOME 确认能看到。
say "→ 自检 Claude/Kiro 会话目录可见性(复现 server 运行时 HOME=$HOME)"
env -i PATH="$PATH_ENV" HOME="$HOME" "$VENV/bin/python" - <<'PY'
import os
for label, p in (("Claude", "~/.claude/projects"), ("Kiro", "~/.kiro/sessions")):
    full = os.path.expanduser(p)
    if os.path.isdir(full):
        print(f"   ✓ {label}: {full}({len(os.listdir(full))} 项)")
    else:
        print(f"   · {label}: {full} 不存在 —— 该工具没装或还没会话,server 会自动跳过(非错误)")
PY

# ---------- 6) 写入 Quick 的 mcp_config.json(备份 + 合并;DAILY_LOG_NO_WRITE=1 可跳过)----------
CONFIG_ENTRY_HINT=$(cat <<EOF
  "daily-log-collector": {
    "command": "$VENV/bin/python",
    "args": ["$SERVER_DIR/server.py"],
    "env": { "PATH": "$PATH_ENV", "DAILY_LOG_DATA_DIR": "$DATA_DIR" },
    "_quick": { "startupTimeout": 300 }
  }
EOF
)

if [ "${DAILY_LOG_NO_WRITE:-}" = "1" ]; then
  say ""
  say "✅ 安装完成(未改配置:DAILY_LOG_NO_WRITE=1)。把下面这条加进 Quick 的 mcpServers(注意逗号):"
  say ""
  printf '%s\n' "$CONFIG_ENTRY_HINT"
else
  QW="$HOME/.quickwork"
  say "→ 写入 Quick 配置(合并 daily-log-collector,改前自动 .bak 备份)"
  # 定位 active profile 的 mcp_config.json(Quick 实际读取的那份);根配置若存在也一并更新。
  targets_out="$("$VENV/bin/python" - "$QW" <<'PY'
import json, os, sys
qw = sys.argv[1]
out = []
prof = os.path.join(qw, "profiles.json")
if os.path.isfile(prof):
    try:
        d = json.load(open(prof))
        la = d.get("last_active")
        for e in d.get("entries", []):
            if e.get("id") == la and e.get("data_path"):
                out.append(os.path.join(qw, e["data_path"], "mcp_config.json"))
                break
    except Exception:
        pass
root = os.path.join(qw, "mcp_config.json")
if os.path.isfile(root):
    out.append(root)
if not out:                         # 都没有 → 至少写 active profile 或根
    out.append(root)
print("\n".join(dict.fromkeys(out)))  # 去重、保序
PY
)"
  wrote_any=0
  while IFS= read -r cfg; do
    [ -z "$cfg" ] && continue
    "$VENV/bin/python" - "$cfg" "$VENV/bin/python" "$SERVER_DIR/server.py" "$PATH_ENV" "$DATA_DIR" <<'PY'
import json, os, shutil, sys
cfg, cmd, srv, path_env, data_dir = sys.argv[1:6]
os.makedirs(os.path.dirname(cfg), exist_ok=True)
data, had = {}, os.path.exists(cfg)
if had:
    shutil.copy2(cfg, cfg + ".bak")
    try:
        data = json.load(open(cfg))
    except Exception:
        data = {}
if not isinstance(data, dict):
    data = {}
data.setdefault("mcpServers", {})["daily-log-collector"] = {
    "command": cmd,
    "args": [srv],
    "env": {"PATH": path_env, "DAILY_LOG_DATA_DIR": data_dir},
    "_quick": {"startupTimeout": 300},
}
json.dump(data, open(cfg, "w"), ensure_ascii=False, indent=2)
print(f"   ✓ {cfg}" + ("  (原文件已备份 .bak)" if had else "  (新建)"))
PY
    wrote_any=1
  done <<< "$targets_out"
  say ""
  if [ "$wrote_any" = "1" ]; then
    say "✅ 安装完成,配置已写入。重启 Quick(或在界面里 reload MCP servers)即可加载。"
  else
    say "⚠ 没能定位到 Quick 配置文件。手动把下面这条加进 mcpServers:"; say ""
    printf '%s\n' "$CONFIG_ENTRY_HINT"
  fi
fi

say ""
say "自测(可选):  DAILY_LOG_DATA_DIR=\"$DATA_DIR\" \"$VENV/bin/python\" \"$SERVER_DIR/server.py\" --selftest 7"
