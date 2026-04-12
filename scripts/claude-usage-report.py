#!/usr/bin/env python3
"""
Claude Code weekly usage analyzer.
Reads JSONL session files from ~/.claude/ and produces a token/cost report.

Usage:
    python3 claude-usage-report.py [--days N] [--json] [--project PROJECT_PATH]
"""
import json
import os
import glob
import sys
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path


CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Opus pricing per 1M tokens
PRICING = {
    "opus": {"input": 15, "output": 75, "cache_read": 1.875, "cache_write": 18.75},
    "sonnet": {"input": 3, "output": 15, "cache_read": 0.30, "cache_write": 3.75},
    "haiku": {"input": 0.80, "output": 4, "cache_read": 0.08, "cache_write": 1.0},
}


def analyze_jsonl(path: str) -> dict:
    """Parse a Claude Code JSONL session file and extract usage stats."""
    stats = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "messages": 0,
        "user_msgs": 0,
        "assistant_msgs": 0,
        "tool_calls": 0,
        "tool_types": defaultdict(int),
        "subagent_launches": 0,
        "skill_calls": 0,
        "models": set(),
        "first_ts": None,
        "last_ts": None,
    }
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")
                ts = data.get("timestamp", "")
                if ts:
                    if stats["first_ts"] is None:
                        stats["first_ts"] = ts
                    stats["last_ts"] = ts

                if msg_type == "user":
                    stats["user_msgs"] += 1
                    stats["messages"] += 1
                elif msg_type == "assistant":
                    stats["assistant_msgs"] += 1
                    stats["messages"] += 1

                    message = data.get("message", {})
                    if not isinstance(message, dict):
                        continue

                    usage = message.get("usage", {})
                    stats["input_tokens"] += usage.get("input_tokens", 0)
                    stats["output_tokens"] += usage.get("output_tokens", 0)
                    stats["cache_read"] += usage.get("cache_read_input_tokens", 0)
                    stats["cache_creation"] += usage.get("cache_creation_input_tokens", 0)

                    model = message.get("model", "")
                    if model:
                        stats["models"].add(model)

                    content = message.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                tool_name = block.get("name", "unknown")
                                stats["tool_calls"] += 1
                                stats["tool_types"][tool_name] += 1
                                if tool_name == "Agent":
                                    stats["subagent_launches"] += 1
                                    inp = block.get("input", {})
                                    sa_type = inp.get("subagent_type", "general-purpose")
                                    stats["tool_types"][f"Agent:{sa_type}"] += 1
                                if tool_name == "Skill":
                                    stats["skill_calls"] += 1
                                    inp = block.get("input", {})
                                    skill_name = inp.get("skill", "unknown")
                                    stats["tool_types"][f"Skill:{skill_name}"] += 1
    except Exception as e:
        stats["error"] = str(e)
    return stats


def estimate_cost(input_tok, output_tok, cache_read, cache_creation, model="opus"):
    p = PRICING.get(model, PRICING["opus"])
    return {
        "input": (input_tok / 1e6) * p["input"],
        "output": (output_tok / 1e6) * p["output"],
        "cache_read": (cache_read / 1e6) * p["cache_read"],
        "cache_write": (cache_creation / 1e6) * p["cache_write"],
    }


def find_session_files(days: int, project_filter: str = None):
    cutoff = datetime.now() - timedelta(days=days)
    all_files = []
    search_dirs = []

    if project_filter:
        search_dirs = [PROJECTS_DIR / project_filter]
    else:
        for d in PROJECTS_DIR.iterdir():
            if d.is_dir():
                search_dirs.append(d)

    for base_dir in search_dirs:
        for f in glob.glob(str(base_dir / "**" / "*.jsonl"), recursive=True):
            mtime = os.path.getmtime(f)
            mdate = datetime.fromtimestamp(mtime)
            if mdate >= cutoff:
                all_files.append((f, mdate, str(base_dir.name)))
    return all_files


def generate_report(days: int = 7, project_filter: str = None, output_json: bool = False):
    all_files = find_session_files(days, project_filter)
    all_files.sort(key=lambda x: x[1])

    main_sessions = [(f, d, p) for f, d, p in all_files if "/subagents/" not in f]
    subagent_files = [(f, d, p) for f, d, p in all_files if "/subagents/" in f]

    # Aggregate
    total = defaultdict(int)
    total["tool_types"] = defaultdict(int)
    total["models"] = set()
    session_details = []

    for fpath, mdate, project in main_sessions:
        s = analyze_jsonl(fpath)
        if s["messages"] == 0:
            continue

        total["sessions"] += 1
        for k in ["input_tokens", "output_tokens", "cache_read", "cache_creation",
                   "messages", "tool_calls", "subagent_launches", "skill_calls"]:
            total[k] += s[k]
        total["models"].update(s["models"])
        for t, c in s["tool_types"].items():
            total["tool_types"][t] += c

        if s["input_tokens"] > 0 or s["output_tokens"] > 0:
            session_details.append({
                "file": os.path.basename(fpath),
                "project": project,
                "date": mdate.strftime("%Y-%m-%d"),
                "input": s["input_tokens"],
                "output": s["output_tokens"],
                "cache_read": s["cache_read"],
                "cache_creation": s["cache_creation"],
                "messages": s["messages"],
                "user_msgs": s["user_msgs"],
                "tool_calls": s["tool_calls"],
                "subagents": s["subagent_launches"],
                "skills": s["skill_calls"],
                "models": list(s["models"]),
                "first_ts": s["first_ts"],
                "last_ts": s["last_ts"],
            })

    sa_total = defaultdict(int)
    sa_total["tool_types"] = defaultdict(int)
    for fpath, _, _ in subagent_files:
        s = analyze_jsonl(fpath)
        for k in ["input_tokens", "output_tokens", "cache_read", "cache_creation", "messages", "tool_calls"]:
            sa_total[k] += s[k]
        for t, c in s["tool_types"].items():
            sa_total["tool_types"][t] += c

    grand = {
        "input": total["input_tokens"] + sa_total["input_tokens"],
        "output": total["output_tokens"] + sa_total["output_tokens"],
        "cache_read": total["cache_read"] + sa_total["cache_read"],
        "cache_creation": total["cache_creation"] + sa_total["cache_creation"],
    }

    opus_cost = estimate_cost(grand["input"], grand["output"], grand["cache_read"], grand["cache_creation"], "opus")
    sonnet_cost = estimate_cost(grand["input"], grand["output"], grand["cache_read"], grand["cache_creation"], "sonnet")

    sa_tok_total = sa_total["input_tokens"] + sa_total["output_tokens"]
    grand_total = grand["input"] + grand["output"]
    sa_pct = (sa_tok_total / grand_total * 100) if grand_total > 0 else 0

    # All tool types combined
    all_tools = defaultdict(int)
    for t, c in total["tool_types"].items():
        all_tools[t] += c
    for t, c in sa_total["tool_types"].items():
        all_tools[t] += c

    # Identify wasteful patterns
    warnings = []
    for sd in session_details:
        if sd["messages"] > 200:
            warnings.append(f"Session {sd['file'][:20]}... has {sd['messages']} messages — consider splitting")
        if sd["subagents"] > 20:
            warnings.append(f"Session {sd['file'][:20]}... launched {sd['subagents']} subagents — review necessity")

    code_reviewer_count = all_tools.get("Agent:superpowers:code-reviewer", 0)
    if code_reviewer_count > 10:
        warnings.append(f"Code reviewer agent launched {code_reviewer_count}x — consider reducing frequency")

    brainstorm_count = all_tools.get("Skill:superpowers:brainstorming", 0)
    if brainstorm_count > 5:
        warnings.append(f"Brainstorming skill invoked {brainstorm_count}x — each adds ~2K tokens to context")

    if grand["cache_read"] > 100_000_000:
        warnings.append(f"Cache read is {grand['cache_read'] / 1e6:.0f}M tokens — lower autoCompactWindow or start fresh sessions more often")

    report = {
        "period_days": days,
        "generated_at": datetime.now().isoformat(),
        "overview": {
            "main_sessions": total["sessions"],
            "subagent_files": len(subagent_files),
            "total_messages": total["messages"],
            "total_tool_calls": total["tool_calls"],
        },
        "tokens": {
            "main": {
                "input": total["input_tokens"],
                "output": total["output_tokens"],
                "cache_read": total["cache_read"],
                "cache_creation": total["cache_creation"],
            },
            "subagents": {
                "input": sa_total["input_tokens"],
                "output": sa_total["output_tokens"],
                "cache_read": sa_total["cache_read"],
                "cache_creation": sa_total["cache_creation"],
            },
            "grand_total": grand,
            "subagent_pct": round(sa_pct, 1),
        },
        "cost_estimate": {
            "opus": {k: round(v, 2) for k, v in opus_cost.items()},
            "opus_total": round(sum(opus_cost.values()), 2),
            "sonnet": {k: round(v, 2) for k, v in sonnet_cost.items()},
            "sonnet_total": round(sum(sonnet_cost.values()), 2),
        },
        "tool_usage": dict(sorted(all_tools.items(), key=lambda x: -x[1])[:20]),
        "top_sessions": sorted(session_details, key=lambda x: -(x["input"] + x["output"]))[:10],
        "warnings": warnings,
    }

    if output_json:
        print(json.dumps(report, indent=2, default=str))
        return report

    # Pretty print
    print("=" * 70)
    print(f"CLAUDE CODE USAGE REPORT — Last {days} days")
    print(f"Generated: {report['generated_at']}")
    print("=" * 70)

    o = report["overview"]
    print(f"\n## Overview")
    print(f"  Sessions: {o['main_sessions']} main + {o['subagent_files']} subagent files")
    print(f"  Messages: {o['total_messages']:,}  |  Tool calls: {o['total_tool_calls']:,}")

    t = report["tokens"]
    print(f"\n## Tokens")
    print(f"  {'':20s} {'Main':>12s} {'Subagents':>12s} {'Total':>12s}")
    print(f"  {'Input':20s} {t['main']['input']:>12,} {t['subagents']['input']:>12,} {t['grand_total']['input']:>12,}")
    print(f"  {'Output':20s} {t['main']['output']:>12,} {t['subagents']['output']:>12,} {t['grand_total']['output']:>12,}")
    print(f"  {'Cache read':20s} {t['main']['cache_read']:>12,} {t['subagents']['cache_read']:>12,} {t['grand_total']['cache_read']:>12,}")
    print(f"  {'Cache creation':20s} {t['main']['cache_creation']:>12,} {t['subagents']['cache_creation']:>12,} {t['grand_total']['cache_creation']:>12,}")
    print(f"  Subagent overhead: {t['subagent_pct']}% of in+out tokens")

    c = report["cost_estimate"]
    print(f"\n## Estimated Cost")
    print(f"  Opus:   ${c['opus_total']:>8.2f}  (in: ${c['opus']['input']:.2f}, out: ${c['opus']['output']:.2f}, cache_r: ${c['opus']['cache_read']:.2f}, cache_w: ${c['opus']['cache_write']:.2f})")
    print(f"  Sonnet: ${c['sonnet_total']:>8.2f}  (potential savings: ${c['opus_total'] - c['sonnet_total']:.2f})")

    print(f"\n## Top Tools")
    for tool, count in list(report["tool_usage"].items())[:15]:
        print(f"  {tool:40s} {count:>6,}")

    print(f"\n## Top Sessions by Cost")
    for i, sd in enumerate(report["top_sessions"][:8]):
        sess_cost = (sd["input"] / 1e6) * 15 + (sd["output"] / 1e6) * 75
        print(f"  #{i+1} {sd['date']} ~${sess_cost:.2f} | msgs:{sd['messages']:>4} agents:{sd['subagents']:>2} skills:{sd['skills']:>2} | {sd['file'][:40]}")

    if report["warnings"]:
        print(f"\n## ⚠ Warnings")
        for w in report["warnings"]:
            print(f"  - {w}")

    print(f"\n## Recommendations")
    if t["grand_total"]["cache_read"] > 100_000_000:
        print("  1. Lower autoCompactWindow (currently 500K) to 200K in settings.json")
    if t["subagent_pct"] > 30:
        print(f"  2. Reduce subagent usage ({t['subagent_pct']}% overhead) — use direct tools when possible")
    agent_cr = report["tool_usage"].get("Agent:superpowers:code-reviewer", 0)
    if agent_cr > 10:
        print(f"  3. Reduce code-reviewer frequency ({agent_cr}x) — review only at milestones")
    skill_count = sum(1 for k in report["tool_usage"] if k.startswith("Skill:"))
    if skill_count > 5:
        print(f"  4. Evaluate skill overhead ({skill_count} skill types) — each adds prompt tokens")
    long_sessions = [s for s in session_details if s["messages"] > 100]
    if long_sessions:
        print(f"  5. Start fresh sessions more often ({len(long_sessions)} sessions had 100+ messages)")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Code usage analyzer")
    parser.add_argument("--days", type=int, default=7, help="Number of days to analyze (default: 7)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--project", type=str, help="Filter to specific project directory name")
    args = parser.parse_args()
    generate_report(days=args.days, project_filter=args.project, output_json=args.json)
