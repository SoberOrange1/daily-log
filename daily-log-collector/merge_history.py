#!/usr/bin/env python3
"""
merge_history.py —— 把 LLM 合成好的"当天三层日志"幂等合并进 history.json,
并据历史重算每个项目的目标时间线(first_seen / last_seen)。

设计要点:
  • 幂等:同一个 (project, date) 重跑就覆盖那一格,不污染其它历史 → 漏跑/重跑都自愈。
  • 目标时间线纯确定性重算:扫全部 entries 里 change.goal_id 的出现日期,
    得到 first_seen/last_seen;title/status 取 payload 提供的定义(缺省沿用旧值)。
  • 单文件 history.json(用户不可见),dashboard 从它生成。

用法(Quick agent 在 run_python 里调):
  python merge_history.py <today_payload.json> <history.json>

today_payload.json 结构(LLM 产出):
{
  "entries": [ { "project","date","status","why":[...],
                 "changes":[{"summary","files":[...],"commit","goal_id"}],
                 "impact_todo":[{"type","text"}] }, ... ],
  "goals": { "<project>": [ {"id","title","status"} ] }   // 可选,目标定义
}
"""
import sys, json, os
from datetime import datetime, timezone, timedelta


def load(path):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "updated_at": None, "entries": {}, "goals": {},
            "summaries": {"daily": {}, "weekly": {}}}


def recompute_goals(history, goal_defs):
    """据 entries 里 change.goal_id 的出现日期,重算每个目标的 first/last_seen。"""
    goals = {}
    for project, days in history["entries"].items():
        pgoals = {}
        for date, entry in days.items():
            for ch in entry.get("changes", []):
                gid = ch.get("goal_id")
                if not gid:
                    continue
                g = pgoals.setdefault(gid, {"id": gid, "first_seen": date, "last_seen": date})
                g["first_seen"] = min(g["first_seen"], date)
                g["last_seen"] = max(g["last_seen"], date)
        # 叠加 payload / 旧库里的 title & status
        prev = history.get("goals", {}).get(project, {})
        defs = {g["id"]: g for g in goal_defs.get(project, [])}
        for gid, g in pgoals.items():
            src = defs.get(gid) or prev.get(gid) or {}
            g["title"] = src.get("title", gid)
            st = src.get("status", "active")
            # 不降级保护:已 delivered 的目标,不因今日 payload 漏标而被改回 active
            if prev.get(gid, {}).get("status") == "delivered" and st == "active":
                st = "delivered"
            g["status"] = st
        if pgoals:
            goals[project] = pgoals
    return goals


def merge(payload: dict, history: dict, retain_days: int = 365,
          today: str | None = None, protect_past: bool = True) -> list:
    """增量合并 payload 进 history(就地修改),按 retain_days 剪枝、重算目标时间线。

    增量语义(核心):
      • 新日期 / 今天 → 写入(今天可反复刷新覆盖);
      • 【已存在的过去日期】→ 冻结不覆盖(避免每次 lookback 重写导致 id churn、断链)。
    返回被冻结跳过的 (project/date) 列表。protect_past=False 可强制覆盖(修数据用)。
    """
    if today is None:
        today = datetime.now(timezone.utc).astimezone().date().isoformat()
    skipped = []
    written_dates = set()                     # 本次真正写入的 entry 日期(供 weekly 判断"该周 entry 是否有变")
    for e in payload.get("entries", []):
        proj, d = e.get("project"), e.get("date")
        if not (proj and d):
            continue
        exists = d in history["entries"].get(proj, {})
        if protect_past and exists and d < today:
            skipped.append(f"{proj}/{d}")     # 过去且已存在 → 冻结
            continue
        history["entries"].setdefault(proj, {})[d] = e
        written_dates.add(d)
    if retain_days:
        cutoff = (datetime.now(timezone.utc).astimezone().date() - timedelta(days=retain_days)).isoformat()
        for proj in list(history["entries"]):
            keep = {d: v for d, v in history["entries"][proj].items() if d >= cutoff}
            if keep:
                history["entries"][proj] = keep
            else:
                del history["entries"][proj]
    history["goals"] = recompute_goals(history, payload.get("goals", {}))

    # summaries(顶层,与 entries 平行):
    #   daily 与 entry 同规则 —— 按其 date(缺省今天)存;缺失的过去日可补、已存在的过去日冻结、今天可刷新。
    #   weekly 是派生聚合,按 week_end 覆盖(可重生成/回溯)。
    now_iso = datetime.now(timezone.utc).astimezone().isoformat()
    S = history.setdefault("summaries", {})
    S.setdefault("daily", {}); S.setdefault("weekly", {})
    ds = payload.get("daily_summary")
    dval, ddate = None, today
    if isinstance(ds, dict) and (ds.get("headline") or ds.get("by_project")):
        dval = {k: v for k, v in ds.items() if k != "date"}   # date 用作 key,不进 value
        ddate = ds.get("date") or today
    elif isinstance(ds, str) and ds.strip():                  # 兼容纯字符串 → 落今天
        dval = {"headline": ds.strip()}
    if dval is not None:
        if protect_past and ddate in S["daily"] and ddate < today:
            skipped.append(f"daily_summary/{ddate}")          # 过去且已存在 → 冻结
        else:
            S["daily"][ddate] = {**dval, "generated_at": now_iso}
    # weekly:过去周(week_end < today)一旦存在就冻结,除非 ①force(用户明确点名更新那周)
    # 或 ②该周 [week_start, week_end] 内本次有 entry 写入(源事实变了 → 允许自动刷新)。
    # 当前/未来周(week_end >= today)可自由刷新。
    ws = payload.get("weekly_summary")
    if isinstance(ws, dict) and isinstance(ws.get("text"), str) and ws["text"].strip():
        wend = ws.get("week_end") or today
        wstart = ws.get("week_start") or wend
        is_past = wend < today
        exists = wend in S["weekly"]
        entries_changed = any(wstart <= wd <= wend for wd in written_dates)
        if protect_past and is_past and exists and not ws.get("force") and not entries_changed:
            skipped.append(f"weekly_summary/{wend}")     # 过去周已存在且无 force/无 entry 变化 → 冻结
        else:
            item = {"text": ws["text"].strip(), "generated_at": now_iso}
            if ws.get("week_start") and ws.get("week_end"):
                item["range"] = [ws["week_start"], ws["week_end"]]
            S["weekly"][wend] = item
    if retain_days:
        scut = (datetime.now(timezone.utc).astimezone().date() - timedelta(days=retain_days)).isoformat()
        for bucket in ("daily", "weekly"):
            S[bucket] = {k: v for k, v in S[bucket].items() if k >= scut}

    history["updated_at"] = now_iso
    return skipped


def main():
    payload_path, history_path = sys.argv[1], sys.argv[2]
    # 第 3 个参数 = 历史保留天数(默认 365;0 = 无限)。可选:180 / 365 / 1095 / 0
    retain_days = int(sys.argv[3]) if len(sys.argv) > 3 else 365
    payload = json.load(open(payload_path, encoding="utf-8"))
    history = load(history_path)
    n = len(payload.get("entries", []))
    merge(payload, history, retain_days)

    os.makedirs(os.path.dirname(os.path.abspath(history_path)), exist_ok=True)
    json.dump(history, open(history_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    ndays = sum(len(v) for v in history["entries"].values())
    ngoals = sum(len(v) for v in history["goals"].values())
    print(f"[merge] +{n} entries (retain {retain_days}d) -> "
          f"{len(history['entries'])} projects / {ndays} project-days / {ngoals} goals")


if __name__ == "__main__":
    main()
