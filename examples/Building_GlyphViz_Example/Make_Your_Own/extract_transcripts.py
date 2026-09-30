"""Step 1: parse Claude Code session transcripts into three flat CSVs.

One pass over the .jsonl files of every project in config.PROJECTS:

    data/sessions.csv      one row per session
    data/turns.csv         one row per prompt and the work that followed it
    data/tool_events.csv   one row per tool call, in order

Nothing downstream re-reads the transcripts, so the (large) .jsonl files are
read exactly once.

    python extract_transcripts.py --list     # which transcript folders exist
    python extract_transcripts.py            # extract everything in PROJECTS

Transcript facts this relies on (checked against Claude Code 2.1.x):

* JSON Lines, one record per line, appended live. One file is one session.
* A `user` record is a prompt only if it carries neither
  `sourceToolAssistantUUID` nor `toolUseResult` -- those two mark tool results,
  which outnumber real prompts about 20 to 1. `isMeta` records, compaction
  summaries and `<command-name>`-style bodies are harness plumbing.
* `assistant.message.content` holds the interesting blocks: `text`,
  `thinking`, `tool_use`.
* Thinking TEXT is stored only for some models; others write the block with an
  encrypted signature and an empty string. So the block COUNT is comparable
  across sessions and the character count is not -- the scenes use the count.
* Wall-clock span is meaningless (a resumed session can span weeks). Active
  time -- the sum of gaps between records of at most IDLE_GAP_S -- is the
  honest duration.
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import re
import statistics
from datetime import datetime

import config

IDLE_GAP_S = 300.0          # gaps longer than this are "away", not working

META_PREFIXES = ("<command-name>", "<local-command", "<command-message>",
                 "Caveat:", "[Request interrupted", "<system-reminder>",
                 # A background task finishing is written as a `user` record
                 # with no tool-result marker; it is not something you typed.
                 "<task-notification>")

# IDE context the VS Code extension prepends to a real prompt ("The user opened
# the file ..."). Stripped, not skipped: the prompt you typed follows it.
IDE_CONTEXT = re.compile(r"<(ide_[a-z_]+)>.*?</\1>", re.S)

# Tool taxonomy: four families, the four things the work alternates between.
TOOL_FAMILY = {
    "Read": "explore", "Grep": "explore", "Glob": "explore",
    "WebSearch": "explore", "WebFetch": "explore", "ToolSearch": "explore",
    "Edit": "mutate", "Write": "mutate", "NotebookEdit": "mutate",
    "MultiEdit": "mutate",
    "Bash": "execute", "PowerShell": "execute",
    "TodoWrite": "meta", "AskUserQuestion": "meta", "Agent": "meta",
    "Task": "meta", "Skill": "meta", "EnterPlanMode": "meta",
    "ExitPlanMode": "meta",
}
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")

RX_COMMIT = re.compile(r"git\s+(commit|-c\s+\S+\s+commit)")
RX_TEST = re.compile(r"\b(pytest|npm (run )?test|vitest|jest|cargo test|go test)\b")


def path_cat(p: str) -> str:
    for name, rx in config.PATH_CATS:
        if rx.search(p):
            return name
    return "other"


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def nwords(s):
    return len(re.findall(r"\S+", s or ""))


def first_line(s, n=110):
    """First non-empty line of a prompt, squeezed and truncated."""
    for ln in (s or "").splitlines():
        ln = ln.strip()
        if ln:
            return re.sub(r"\s+", " ", ln)[:n]
    return ""


def strip_reminders(s):
    s = re.sub(r"<system-reminder>.*?</system-reminder>", "", s or "", flags=re.S)
    # Task notifications can also arrive APPENDED to a real prompt when a
    # background task finishes while you are typing -- drop them, keep you.
    s = re.sub(r"<task-notification>.*?(</task-notification>|$)", "", s, flags=re.S)
    return IDE_CONTEXT.sub("", s)


def read_session(fp, project):
    """Return (session_dict, turn_dicts, tool_event_dicts) for one transcript."""
    sid = os.path.basename(fp)[:-6]
    recs = []
    for line in open(fp, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    if not recs:
        return None, [], []

    # ---- session-wide: timestamps, active time, titles ----
    stamps = sorted(t for t in (parse_ts(r.get("timestamp")) for r in recs) if t)
    if not stamps:
        return None, [], []
    active_s = 0.0
    active_at = {stamps[0]: 0.0}        # timestamp -> cumulative active seconds
    for a, b in zip(stamps, stamps[1:]):
        gap = (b - a).total_seconds()
        if 0 <= gap <= IDLE_GAP_S:
            active_s += gap
        active_at[b] = active_s

    # The auto-title is rewritten as the session goes; the last one is best.
    titles = [r["aiTitle"] for r in recs if r.get("type") == "ai-title" and r.get("aiTitle")]
    models = collections.Counter()

    # ---- which tool calls came back as errors ----
    err_ids = set()
    for r in recs:
        if r.get("type") != "user":
            continue
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_result" and b.get("is_error") and b.get("tool_use_id"):
                    err_ids.add(b["tool_use_id"])

    # ---- walk the turns ----
    turns, events = [], []
    cur = None
    seq = 0

    def close(t):
        if t is None:
            return
        t["duration_min"] = round(
            (active_at.get(t["_t_last"], 0.0) - active_at.get(t["_t0"], 0.0)) / 60.0, 2)
        for k in ("_t_last", "_t0"):
            t.pop(k)
        turns.append(t)

    for r in recs:
        typ = r.get("type")
        tm = parse_ts(r.get("timestamp"))

        if typ == "user":
            if r.get("sourceToolAssistantUUID") or r.get("toolUseResult") is not None:
                continue
            if r.get("isMeta") or r.get("isCompactSummary"):
                continue
            c = (r.get("message") or {}).get("content")
            blocks = c if isinstance(c, list) else [{"type": "text", "text": c or ""}]
            raw = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            n_img = sum(1 for b in blocks if b.get("type") == "image")
            n_doc = sum(1 for b in blocks if b.get("type") == "document")
            txt = strip_reminders(raw).strip()
            if not txt and not n_img and not n_doc:
                continue
            if txt.startswith(META_PREFIXES) and not n_img and not n_doc:
                continue
            close(cur)
            cur = {
                "session": sid, "turn": len(turns), "ts": tm.isoformat() if tm else "",
                "t_active_min": round(active_at.get(tm, 0.0) / 60.0, 2) if tm else 0.0,
                "prompt_words": nwords(txt), "prompt_chars": len(txt),
                "prompt_first_line": first_line(txt, 200),
                "images": n_img, "documents": n_doc,
                "asst_msgs": 0, "asst_words": 0, "think_blocks": 0,
                "tools": 0, "errors": 0, "commits": 0, "tests": 0,
                "_t0": tm, "_t_last": tm,
            }

        elif typ == "assistant" and cur is not None:
            msg = r.get("message") or {}
            models[msg.get("model")] += 1
            cur["asst_msgs"] += 1
            if tm:
                cur["_t_last"] = tm
            for b in msg.get("content", []) or []:
                bt = b.get("type")
                if bt == "text":
                    cur["asst_words"] += nwords(b.get("text"))
                elif bt == "thinking":
                    cur["think_blocks"] += 1
                elif bt == "tool_use":
                    name = b.get("name") or "?"
                    inp = b.get("input") or {}
                    is_err = 1 if b.get("id") in err_ids else 0
                    target, cat = "", "misc"
                    if name in EDIT_TOOLS or name == "Read":
                        path = (inp.get("file_path") or inp.get("notebook_path")
                                or "").replace("/", "\\")
                        cat = path_cat(path)
                        target = os.path.basename(path)
                    elif name in ("Bash", "PowerShell"):
                        cmdtxt = inp.get("command") or ""
                        if RX_COMMIT.search(cmdtxt):
                            cur["commits"] += 1
                            cat = "commit"
                        elif RX_TEST.search(cmdtxt):
                            cur["tests"] += 1
                            cat = "test"
                        else:
                            cat = "shell"
                        target = first_line(cmdtxt, 70)
                    elif name in ("Grep", "Glob"):
                        target = first_line(inp.get("pattern") or "", 50)
                        cat = "search"
                    elif name in ("Agent", "Task"):
                        target = first_line(inp.get("description") or "", 50)
                        cat = "agent"
                    cur["tools"] += 1
                    cur["errors"] += is_err
                    seq += 1
                    events.append({
                        "session": sid, "turn": cur["turn"], "seq": seq,
                        "turn_seq": cur["tools"] - 1,
                        "tool": name, "family": TOOL_FAMILY.get(name, "meta"),
                        "cat": cat, "target": target, "is_error": is_err,
                    })
    close(cur)

    # ---- roll up the session row ----
    fam = collections.Counter(e["family"] for e in events)
    cats = collections.Counter(e["cat"] for e in events if e["tool"] in EDIT_TOOLS)
    edited = {(e["cat"], e["target"]) for e in events if e["tool"] in EDIT_TOOLS}
    local0 = stamps[0].astimezone()      # your local calendar, not UTC's
    sess = {
        "session": sid,
        "project": project,
        "title": titles[-1] if titles else "",
        "start": stamps[0].isoformat(),
        "date": local0.date().isoformat(),
        "hour_local": local0.hour,
        "wall_min": round((stamps[-1] - stamps[0]).total_seconds() / 60.0, 1),
        "active_min": round(active_s / 60.0, 1),
        "prompts": len(turns),
        "prompt_words": sum(t["prompt_words"] for t in turns),
        "images": sum(t["images"] for t in turns),
        "documents": sum(t["documents"] for t in turns),
        "asst_msgs": sum(t["asst_msgs"] for t in turns),
        "asst_words": sum(t["asst_words"] for t in turns),
        "think_blocks": sum(t["think_blocks"] for t in turns),
        "tools": len(events),
        "errors": sum(t["errors"] for t in turns),
        "commits": sum(t["commits"] for t in turns),
        "tests": sum(t["tests"] for t in turns),
        "files_edited": len(edited),
        "model": models.most_common(1)[0][0] if models else "",
        **{f"fam_{k}": fam.get(k, 0) for k in ("explore", "mutate", "execute", "meta")},
        **{f"cat_{name}": cats.get(name, 0)
           for name in [c[0] for c in config.PATH_CATS] + ["other"]},
    }
    return sess, turns, events


def project_dir(folder):
    return folder if os.path.isabs(folder) else os.path.join(config.TRANSCRIPT_ROOT, folder)


def list_folders():
    root = config.TRANSCRIPT_ROOT
    if not os.path.isdir(root):
        raise SystemExit(f"no transcript folder at {root} (set CLAUDE_PROJECTS_DIR?)")
    print(f"transcript folders under {root}:\n")
    rows = []
    for name in sorted(os.listdir(root)):
        files = glob.glob(os.path.join(root, name, "*.jsonl"))
        if files:
            rows.append((name, len(files), sum(os.path.getsize(f) for f in files)))
    for name, n, size in rows:
        print(f"  {n:4d} sessions  {size / 1e6:7.1f} MB   {name}")
    print("\nCopy the folder name(s) you want into PROJECTS in config.py.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true",
                    help="list the transcript folders on this machine and exit")
    args = ap.parse_args()
    if args.list:
        return list_folders()

    todo = [p for p in config.PROJECTS if not p["folder"].startswith("<")]
    if not todo:
        print("config.PROJECTS still holds the placeholder folder name.\n")
        list_folders()
        raise SystemExit(1)

    os.makedirs(config.DATA_DIR, exist_ok=True)
    sessions, turns, events = [], [], []
    for p in todo:
        src = project_dir(p["folder"])
        files = sorted(glob.glob(os.path.join(src, "*.jsonl")))
        if not files:
            raise SystemExit(f"no transcripts under {src} -- see --list")
        n0 = len(sessions)
        for fp in files:
            s, t, e = read_session(fp, p["key"])
            if s is None:
                continue
            sessions.append(s)
            turns.extend(t)
            events.extend(e)
        print(f"parsed {len(files):4d} transcripts as '{p['key']}'"
              f" ({len(sessions) - n0} usable)")

    if not sessions:
        raise SystemExit("no usable sessions found")
    # turns/tool_events join back on the session id (the transcript's filename
    # UUID), so it has to be unique across every folder read.
    dupes = len(sessions) - len({s["session"] for s in sessions})
    if dupes:
        raise SystemExit(f"{dupes} session ids appear in more than one project "
                         "-- is the same folder listed twice?")
    sessions.sort(key=lambda r: r["start"])

    def dump(name, rows):
        path = os.path.join(config.DATA_DIR, name)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["session"])
            w.writeheader()
            w.writerows(rows)
        print(f"  {name:18s} {len(rows):6d} rows")

    print()
    dump("sessions.csv", sessions)
    dump("turns.csv", turns)
    dump("tool_events.csv", events)

    am = [s["active_min"] for s in sessions]
    print(f"\n{len(sessions)} sessions, {sum(am) / 60.0:.1f} active hours, "
          f"{sum(s['prompts'] for s in sessions)} prompts, {len(events)} tool calls, "
          f"{sum(s['commits'] for s in sessions)} commits")
    print(f"{sessions[0]['date']} -> {sessions[-1]['date']}, "
          f"median session {statistics.median(am):.1f} active minutes")


if __name__ == "__main__":
    main()
