#!/usr/bin/env python3
"""
Ghi BỔ SUNG vào .ai-log/session.jsonl các prompt thật đã gửi cho Claude Code
nhưng chưa được hook ghi lại (vd. làm ở thư mục khác trước khi có P-027).

Nguồn: transcript Claude Code thật trong ~/.claude/projects/<thư-mục-dự-án>/*.jsonl.
Mỗi dòng giữ nguyên prompt gốc và timestamp gốc; event = "BackfilledLog" và có
trường "source" để người chấm phân biệt được với log realtime. KHÔNG sửa nội dung.

Ví dụ:
  python scripts/backfill_from_claude.py --project-dir "d--Vinuni-endgame-cam-lidar-radar-cam-lidar-radar-ws" --dry-run
  python scripts/backfill_from_claude.py --project-dir "d--Vinuni-endgame-cam-lidar-radar-cam-lidar-radar-ws"

Chạy lại nhiều lần an toàn: entry_id đã có trong session.jsonl sẽ bị bỏ qua.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))
_NOISE = re.compile(r"<(system-reminder|local-command-caveat|local-command-stdout|command-name|command-message|command-args|task-notification)>.*?</\1>", re.S)
# Tin nhắn do hệ thống/Claude tự sinh, không phải người dùng gõ
_AUTO = ("[SYSTEM", "Caveat:", "This session is being continued", "Continue from where you left off", "Another Claude session sent")
_PROJECTS = Path.home() / ".claude" / "projects"


def git(*args):
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def user_text(msg):
    c = msg.get("content")
    if isinstance(c, list):
        c = "".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    if not isinstance(c, str):
        return ""
    return _NOISE.sub("", c).strip()


def collect(project_dir):
    out = []
    for f in sorted((_PROJECTS / project_dir).glob("*.jsonl")):
        for line in open(f, encoding="utf-8", errors="ignore"):
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if j.get("type") != "user" or j.get("isSidechain") or j.get("toolUseResult") is not None:
                continue
            text = user_text(j.get("message", {}))
            if not text or text.startswith(_AUTO):
                continue
            if re.fullmatch(r"(\[Image[^\]]*\]\s*)+", text):   # chỉ có tham chiếu ảnh, không có chữ
                continue
            out.append((j.get("timestamp", ""), j.get("sessionId", f.stem), j.get("uuid", ""), text, j.get("message", {}).get("model", ""), f.name))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", required=True, action="append", help="tên thư mục trong ~/.claude/projects (lặp lại được)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in, không ghi")
    args = ap.parse_args()

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_file = log_dir / "session.jsonl"
    seen = set()
    if log_file.exists():
        for l in open(log_file, encoding="utf-8"):
            try:
                seen.add(json.loads(l).get("entry_id"))
            except json.JSONDecodeError:
                pass

    repo = (git("remote", "get-url", "origin").rstrip("/").split("/")[-1] or "").removesuffix(".git")
    base = {"repo": repo, "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "commit": git("rev-parse", "--short", "HEAD"), "student": git("config", "user.email")}
    if not base["student"]:
        sys.exit("git user.email chưa đặt: git config user.email \"you@...\"")

    entries, dup = [], set()   # dup: transcript của phiên resume chép lại lịch sử cũ -> bỏ trùng theo (giờ, nội dung)
    for pd in args.project_dir:
        if not (_PROJECTS / pd).is_dir():
            sys.exit(f"không thấy {_PROJECTS / pd}")
        for ts, sid, uid, text, model, fname in collect(pd):
            eid = f"backfill-{sid[:8]}-{uid[:8]}"
            if eid in seen or (ts, text) in dup:
                continue
            dup.add((ts, text))
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(VN_TZ).isoformat() if ts else ""
            entries.append({"ts": t, "tool": "claude", "event": "BackfilledLog", "entry_id": eid, "session_id": sid, "model": model or "claude",
                            **base, "prompt": text[:1000], "source": f"claude-code transcript {pd}/{fname} (ghi bổ sung, timestamp gốc)"})

    for e in entries:
        print(f"{e['ts'][:19]}  {e['prompt'][:90].replace(chr(10), ' ')}")
    print(f"\n{len(entries)} prompt mới" + (" (dry-run, chưa ghi)" if args.dry_run else ""))
    if args.dry_run or not entries:
        return
    log_dir.mkdir(exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"đã ghi vào {log_file}")


if __name__ == "__main__":
    main()
