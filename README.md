# daily-log-collector

一个跑在本机的 **Quick Desktop 本地 MCP server**。Quick 在沙箱里够不到本地文件和 git,
这个 server 作为"越狱口",在本机读取你的开发痕迹(Claude Code 会话、Kiro 会话、git 提交),
做确定性抽取 + 降噪,把结构化事件递给 Quick,让 Quick 里的 agent 合成一份**三层开发日志**
并渲染成 dashboard。

- **为什么做** ← 你发给 AI 的 prompt
- **改动** ← AI 的文件编辑 + git commit
- **影响 / 待办** ← 决策点问题 + 会话收尾总结

---

## 安装(三步)

### 前提
- 一台 macOS / Linux 机器,上面有**任意一个 Python 3.10+**(在哪、是不是 conda 都行,
  安装脚本会自动检测)。没有的话先装一个:`brew install python` 或 pyenv / miniconda。
- (可选)真正的 `git` —— 用于采集 commit。macOS 自带的 `/usr/bin/git` 若只是 Xcode 桩,
  安装脚本会提示;装真 git:`brew install git`。

### 第 1 步:运行安装脚本
```bash
bash daily-log-collector/install.sh
```
它会自动:
1. 检测可用的 Python 3.10+(过滤掉不能跑的 Xcode 桩)
2. 在部署目录建一个**隔离 venv**,钉死安装 `mcp==1.29.0`(不污染你的 Python 环境)
3. 部署 server 到 `~/.quickwork/mcp-servers/daily-log-collector/`
4. 历史数据放到独立的 `~/.daily-log-collector/`(重装代码不丢历史;旧位置会自动迁移)
5. 自检 git 与 Claude/Kiro 会话目录的可见性
6. 把 `daily-log-collector` 合并进 Quick 的 `mcp_config.json`(改前自动 `.bak` 备份)

> 想只打印配置、不自动写入:`DAILY_LOG_NO_WRITE=1 bash .../install.sh`
> 想自定义数据目录:`DAILY_LOG_DATA_DIR=/你的/路径 bash .../install.sh`

### 第 2 步:重启 Quick
重启 Quick(或在界面里 reload MCP servers),让它加载新注册的 `daily-log-collector`。
加载后,它的工具会显示为 **always allow**(只读工具,Quick 自动放行)。

### 第 3 步:让 Quick 配置 daily-log agent
把仓库里的 **`quick-set-up.md`** 拖进 Quick,并说一句:

> 照这个文档配置一个 daily-log agent。

Quick 的 Agent Builder 会按该文档创建 agent、挂上 daily-log-collector 连接器、
写好合成工作流指令,并**询问你希望每天几点自动汇总**(默认 17:30)。

---

## 验证(可选)
不经过 Quick,直接看采集结果:
```bash
"~/.quickwork/mcp-servers/daily-log-collector/.venv/bin/python" \
  "~/.quickwork/mcp-servers/daily-log-collector/server.py" --selftest 7
```

---

## 目录布局

```
~/.quickwork/mcp-servers/daily-log-collector/   # 代码 + 隔离 venv(可整目录重装)
  server.py  merge_history.py  render_dashboard.py  .venv/
~/.daily-log-collector/                          # 历史数据(独立,重装不丢)
  history.json
```

## 卸载
删掉上面两个目录,再从 Quick 的 `mcp_config.json` 里移除 `daily-log-collector` 那一项即可。

---

## 采集范围与路径(供排查)
| 数据 | server 从哪读 | 依赖 |
|---|---|---|
| Claude 会话 | `~/.claude/projects/`(固定) | HOME |
| Kiro 会话 | `~/.kiro/sessions/`(固定) | HOME |
| git commit | 从上面发现的项目目录**向上找 `.git`**,在仓库根跑 `git log` | `env.PATH` 上有真 git |

项目名 = 归一化到项目根(所在 git 仓库根,否则路径本身)后的末段目录名,不依赖任何
自定义根目录。想额外纳入"没有 AI 会话的纯 git 仓库",可设 `DAILY_LOG_EXTRA_GIT_ROOTS`
(逗号分隔)。
