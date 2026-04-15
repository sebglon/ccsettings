#!/usr/bin/env python3
"""
Claude Code usage analyzer.
Reads JSONL session files from ~/.claude/ and produces a token/cost report.

Usage:
    python3 claude-usage-report.py [--days N] [--json] [--llm] [--project PROJECT_PATH]

Modes:
    (default)  Human-readable terminal report
    --json     Raw JSON data for programmatic use
    --llm      Pre-analyzed markdown optimized for LLM consumption (recommended for skill usage)
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

# Pricing per 1M tokens — https://docs.anthropic.com/en/docs/about-claude/models
# Cache write uses 5-minute TTL rate (Claude Code default). 1-hour TTL is higher.
# Last updated: 2026-04-15
PRICING = {
    "opus": {"input": 5, "output": 25, "cache_read": 0.50, "cache_write": 6.25},
    "sonnet": {"input": 3, "output": 15, "cache_read": 0.30, "cache_write": 3.75},
    "haiku": {"input": 1, "output": 5, "cache_read": 0.10, "cache_write": 1.25},
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
    costs = {
        "input": (input_tok / 1e6) * p["input"],
        "output": (output_tok / 1e6) * p["output"],
        "cache_read": (cache_read / 1e6) * p["cache_read"],
        "cache_write": (cache_creation / 1e6) * p["cache_write"],
    }
    costs["total"] = sum(costs.values())
    return costs


def session_duration_str(first_ts, last_ts):
    """Return human-readable duration between two ISO timestamps."""
    if not first_ts or not last_ts:
        return "unknown"
    try:
        fmt_opts = ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f"]
        t0 = t1 = None
        for fmt in fmt_opts:
            try:
                t0 = datetime.strptime(first_ts, fmt)
                break
            except ValueError:
                continue
        for fmt in fmt_opts:
            try:
                t1 = datetime.strptime(last_ts, fmt)
                break
            except ValueError:
                continue
        if not t0 or not t1:
            return "unknown"
        delta = t1 - t0
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m"
        elif hours < 24:
            return f"{hours:.1f}h"
        else:
            return f"{delta.days}d {int(hours % 24)}h"
    except Exception:
        return "unknown"


def read_settings():
    """Read current Claude Code settings.json."""
    settings_path = CLAUDE_DIR / "settings.json"
    if settings_path.exists():
        try:
            return json.loads(settings_path.read_text())
        except Exception:
            return {}
    return {}


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


def generate_report(days: int = 7, project_filter: str = None, output_json: bool = False, output_llm: bool = False):
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
                   "messages", "tool_calls", "subagent_launches", "skill_calls",
                   "user_msgs"]:
            total[k] += s[k]
        total["models"].update(s["models"])
        for t, c in s["tool_types"].items():
            total["tool_types"][t] += c

        if s["input_tokens"] > 0 or s["output_tokens"] > 0 or s["cache_read"] > 0:
            sess_cost = estimate_cost(s["input_tokens"], s["output_tokens"],
                                      s["cache_read"], s["cache_creation"], "opus")
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
                "duration": session_duration_str(s["first_ts"], s["last_ts"]),
                "cost_opus": round(sess_cost["total"], 2),
                "cost_breakdown": {k: round(v, 2) for k, v in sess_cost.items()},
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

    # Cost breakdown percentages
    total_opus = opus_cost["total"]
    cost_pcts = {}
    if total_opus > 0:
        for k in ["input", "output", "cache_read", "cache_write"]:
            cost_pcts[k] = round(opus_cost[k] / total_opus * 100, 1)

    # Daily breakdown
    daily = defaultdict(lambda: {"sessions": 0, "messages": 0, "tool_calls": 0,
                                  "input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
    for sd in session_details:
        d = sd["date"]
        daily[d]["sessions"] += 1
        daily[d]["messages"] += sd["messages"]
        daily[d]["tool_calls"] += sd["tool_calls"]
        daily[d]["input"] += sd["input"]
        daily[d]["output"] += sd["output"]
        daily[d]["cache_read"] += sd["cache_read"]
        daily[d]["cache_creation"] += sd["cache_creation"]
    # Compute daily costs
    for d in daily:
        dc = estimate_cost(daily[d]["input"], daily[d]["output"],
                           daily[d]["cache_read"], daily[d]["cache_creation"], "opus")
        daily[d]["cost_opus"] = round(dc["total"], 2)

    # Identify wasteful patterns
    warnings = []
    for sd in session_details:
        if sd["messages"] > 200:
            warnings.append(f"Session {sd['file'][:20]}... has {sd['messages']} messages (duration: {sd['duration']}, cost: ${sd['cost_opus']:.2f})")
        if sd["subagents"] > 20:
            warnings.append(f"Session {sd['file'][:20]}... launched {sd['subagents']} subagents")

    code_reviewer_count = all_tools.get("Agent:superpowers:code-reviewer", 0)
    if code_reviewer_count > 10:
        warnings.append(f"Code reviewer agent launched {code_reviewer_count}x — consider reducing frequency")

    brainstorm_count = all_tools.get("Skill:superpowers:brainstorming", 0)
    if brainstorm_count > 5:
        warnings.append(f"Brainstorming skill invoked {brainstorm_count}x — each adds ~2K tokens to context")

    if grand["cache_read"] > 100_000_000:
        warnings.append(f"Cache read is {grand['cache_read'] / 1e6:.0f}M tokens — sessions are too long or autoCompactWindow too high")

    # Read current settings for context-aware recommendations
    settings = read_settings()
    current_model = settings.get("model", "unknown")
    current_compact = settings.get("autoCompactWindow", "default")

    # Sort sessions by total cost (including cache)
    sessions_by_cost = sorted(session_details, key=lambda x: -x["cost_opus"])

    report = {
        "period_days": days,
        "generated_at": datetime.now().isoformat(),
        "settings": {
            "model": current_model,
            "autoCompactWindow": current_compact,
        },
        "overview": {
            "main_sessions": total["sessions"],
            "subagent_files": len(subagent_files),
            "total_messages": total["messages"],
            "total_user_messages": total["user_msgs"],
            "total_tool_calls": total["tool_calls"],
            "avg_messages_per_session": round(total["messages"] / max(total["sessions"], 1)),
            "avg_tools_per_session": round(total["tool_calls"] / max(total["sessions"], 1)),
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
            "opus_total": round(total_opus, 2),
            "sonnet": {k: round(v, 2) for k, v in sonnet_cost.items()},
            "sonnet_total": round(sonnet_cost["total"], 2),
            "savings_if_sonnet": round(total_opus - sonnet_cost["total"], 2),
            "cost_distribution_pct": cost_pcts,
        },
        "daily_breakdown": {d: daily[d] for d in sorted(daily.keys())},
        "tool_usage": dict(sorted(all_tools.items(), key=lambda x: -x[1])[:20]),
        "top_sessions": sessions_by_cost[:10],
        "warnings": warnings,
    }

    if output_json:
        print(json.dumps(report, indent=2, default=str))
        return report

    if output_llm:
        print_llm_report(report, session_details)
        return report

    print_human_report(report, session_details)
    return report


def print_llm_report(report, session_details):
    """Output pre-analyzed markdown optimized for LLM consumption."""
    days = report["period_days"]
    settings = report["settings"]
    o = report["overview"]
    t = report["tokens"]
    c = report["cost_estimate"]
    pcts = c.get("cost_distribution_pct", {})
    daily = report["daily_breakdown"]

    lines = []
    lines.append(f"# Claude Code Usage Report — Last {days} days")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")

    # Current settings context
    lines.append("## Current Settings")
    lines.append(f"- Default model: `{settings['model']}`")
    lines.append(f"- autoCompactWindow: `{settings['autoCompactWindow']}`")
    lines.append("")

    # High-level summary
    lines.append("## Summary")
    lines.append(f"- **{o['main_sessions']} sessions**, {o['total_messages']:,} messages, {o['total_tool_calls']:,} tool calls")
    lines.append(f"- **Estimated cost: ${c['opus_total']:,.2f}** (Opus pricing)")
    lines.append(f"- Same usage on Sonnet: ${c['sonnet_total']:,.2f} (savings: ${c['savings_if_sonnet']:,.2f})")
    lines.append(f"- Avg {o['avg_messages_per_session']} messages/session, {o['avg_tools_per_session']} tools/session")
    lines.append(f"- Subagent overhead: {t['subagent_pct']}% of input+output tokens")
    lines.append("")

    # Cost breakdown — the key insight for LLMs
    lines.append("## Cost Breakdown (where money goes)")
    if pcts:
        # Sort by percentage descending
        sorted_pcts = sorted(pcts.items(), key=lambda x: -x[1])
        for k, v in sorted_pcts:
            label = {"input": "Input tokens", "output": "Output tokens",
                     "cache_read": "Cache reads (re-reading context)",
                     "cache_write": "Cache writes (context compaction)"}.get(k, k)
            cost_val = c["opus"].get(k, 0)
            lines.append(f"- **{label}: {v}% (${cost_val:,.2f})**")
    lines.append("")

    top_cost_driver = max(pcts.items(), key=lambda x: x[1])[0] if pcts else "unknown"
    lines.append(f"**Primary cost driver: {top_cost_driver}**")
    if top_cost_driver == "cache_write":
        lines.append("  Cache writes dominate — context is being compacted frequently (long sessions or large context).")
    elif top_cost_driver == "cache_read":
        lines.append("  Cache reads dominate — conversations are long, causing repeated re-reads of full history each turn.")
    elif top_cost_driver == "output":
        lines.append("  Output tokens dominate — lots of generated content per session.")
    lines.append("")

    # Daily trends
    lines.append("## Daily Breakdown")
    lines.append("| Date | Sessions | Messages | Tools | Cost |")
    lines.append("|------|----------|----------|-------|------|")
    for d in sorted(daily.keys()):
        dd = daily[d]
        lines.append(f"| {d} | {dd['sessions']} | {dd['messages']} | {dd['tool_calls']} | ${dd['cost_opus']:,.2f} |")
    lines.append("")

    # Top sessions with full cost
    lines.append("## Top Sessions by Cost")
    lines.append("| # | Date | Duration | Messages | Agents | Skills | Cost | Biggest cost category |")
    lines.append("|---|------|----------|----------|--------|--------|------|-----------------------|")
    for i, sd in enumerate(report["top_sessions"][:8]):
        cb = sd.get("cost_breakdown", {})
        # Find biggest cost category for this session
        biggest = max(((k, v) for k, v in cb.items() if k != "total"), key=lambda x: x[1], default=("?", 0))
        lines.append(f"| {i+1} | {sd['date']} | {sd['duration']} | {sd['messages']} | {sd['subagents']} | {sd['skills']} | ${sd['cost_opus']:,.2f} | {biggest[0]} (${biggest[1]:,.2f}) |")
    lines.append("")

    # Tool usage
    lines.append("## Tool Usage (top 15)")
    lines.append("| Tool | Count |")
    lines.append("|------|-------|")
    for tool, count in list(report["tool_usage"].items())[:15]:
        lines.append(f"| {tool} | {count:,} |")
    lines.append("")

    # Warnings
    if report["warnings"]:
        lines.append("## Warnings")
        for w in report["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    # Pre-computed analysis for LLM
    lines.append("## Pre-computed Analysis")
    lines.append("")

    # Session length analysis
    long_sessions = [s for s in session_details if s["messages"] > 200]
    short_sessions = [s for s in session_details if s["messages"] <= 200]
    if long_sessions:
        long_cost = sum(s["cost_opus"] for s in long_sessions)
        long_pct = (long_cost / c["opus_total"] * 100) if c["opus_total"] > 0 else 0
        lines.append(f"### Session Length")
        lines.append(f"- {len(long_sessions)} sessions with >200 messages account for ${long_cost:,.2f} ({long_pct:.0f}% of total cost)")
        lines.append(f"- {len(short_sessions)} shorter sessions account for ${c['opus_total'] - long_cost:,.2f} ({100-long_pct:.0f}%)")
        lines.append(f"- **Splitting long sessions earlier would reduce cache read/write costs significantly.**")
        lines.append("")

    # Model usage analysis
    opus_sessions = [s for s in session_details if any("opus" in m for m in s["models"])]
    sonnet_sessions = [s for s in session_details if any("sonnet" in m for m in s["models"]) and not any("opus" in m for m in s["models"])]
    mixed_sessions = [s for s in session_details if any("opus" in m for m in s["models"]) and any("sonnet" in m for m in s["models"])]
    lines.append("### Model Usage")
    lines.append(f"- Opus-only sessions: {len(opus_sessions)}")
    lines.append(f"- Sonnet-only sessions: {len(sonnet_sessions)}")
    lines.append(f"- Mixed (Opus+Sonnet) sessions: {len(mixed_sessions)}")
    if settings["model"] and "opus" in str(settings["model"]).lower():
        lines.append(f"- **Default model is set to `{settings['model']}` — sessions may start on Opus unintentionally.**")
    lines.append("")

    # Tool efficiency
    agent_calls = report["tool_usage"].get("Agent", 0)
    direct_reads = report["tool_usage"].get("Read", 0)
    direct_greps = report["tool_usage"].get("Grep", 0)
    direct_globs = report["tool_usage"].get("Glob", 0)
    lines.append("### Tool Efficiency")
    lines.append(f"- Direct tools (Read:{direct_reads}, Grep:{direct_greps}, Glob:{direct_globs}) = {direct_reads+direct_greps+direct_globs} calls")
    lines.append(f"- Agent delegations: {agent_calls} (subagent overhead: {t['subagent_pct']}%)")
    if agent_calls > 0:
        ratio = (direct_reads + direct_greps + direct_globs) / agent_calls
        lines.append(f"- Direct:Agent ratio = {ratio:.1f}:1 {'(good — using direct tools)' if ratio > 5 else '(consider more direct tool usage)'}")
    lines.append("")

    # Skill overhead
    skill_calls = sum(v for k, v in report["tool_usage"].items() if k.startswith("Skill:"))
    if skill_calls > 0:
        lines.append("### Skill Overhead")
        lines.append(f"- {skill_calls} skill invocations across {sum(1 for k in report['tool_usage'] if k.startswith('Skill:'))} skill types")
        lines.append(f"- Each skill injects ~2-5K tokens into context")
        for k, v in report["tool_usage"].items():
            if k.startswith("Skill:"):
                lines.append(f"  - {k}: {v}x")
        lines.append("")

    print("\n".join(lines))


def print_human_report(report, session_details):
    """Output human-readable terminal report."""
    days = report["period_days"]
    o = report["overview"]
    t = report["tokens"]
    c = report["cost_estimate"]

    print("=" * 70)
    print(f"CLAUDE CODE USAGE REPORT — Last {days} days")
    print(f"Generated: {report['generated_at']}")
    print("=" * 70)

    print(f"\n## Overview")
    print(f"  Sessions: {o['main_sessions']} main + {o['subagent_files']} subagent files")
    print(f"  Messages: {o['total_messages']:,}  |  Tool calls: {o['total_tool_calls']:,}")

    print(f"\n## Tokens")
    print(f"  {'':20s} {'Main':>12s} {'Subagents':>12s} {'Total':>12s}")
    print(f"  {'Input':20s} {t['main']['input']:>12,} {t['subagents']['input']:>12,} {t['grand_total']['input']:>12,}")
    print(f"  {'Output':20s} {t['main']['output']:>12,} {t['subagents']['output']:>12,} {t['grand_total']['output']:>12,}")
    print(f"  {'Cache read':20s} {t['main']['cache_read']:>12,} {t['subagents']['cache_read']:>12,} {t['grand_total']['cache_read']:>12,}")
    print(f"  {'Cache creation':20s} {t['main']['cache_creation']:>12,} {t['subagents']['cache_creation']:>12,} {t['grand_total']['cache_creation']:>12,}")
    print(f"  Subagent overhead: {t['subagent_pct']}% of in+out tokens")

    print(f"\n## Estimated Cost")
    print(f"  Opus:   ${c['opus_total']:>8.2f}  (in: ${c['opus']['input']:.2f}, out: ${c['opus']['output']:.2f}, cache_r: ${c['opus']['cache_read']:.2f}, cache_w: ${c['opus']['cache_write']:.2f})")
    print(f"  Sonnet: ${c['sonnet_total']:>8.2f}  (potential savings: ${c['savings_if_sonnet']:.2f})")

    print(f"\n## Top Tools")
    for tool, count in list(report["tool_usage"].items())[:15]:
        print(f"  {tool:40s} {count:>6,}")

    print(f"\n## Top Sessions by Cost")
    for i, sd in enumerate(report["top_sessions"][:8]):
        print(f"  #{i+1} {sd['date']} ${sd['cost_opus']:>8.2f} | {sd['duration']:>6s} | msgs:{sd['messages']:>4} agents:{sd['subagents']:>2} skills:{sd['skills']:>2} | {sd['file'][:36]}")

    if report["warnings"]:
        print(f"\n## Warnings")
        for w in report["warnings"]:
            print(f"  - {w}")

    # Context-aware recommendations
    settings = report["settings"]
    print(f"\n## Recommendations")
    if t["grand_total"]["cache_read"] > 100_000_000:
        cw = settings.get("autoCompactWindow", "unknown")
        print(f"  1. autoCompactWindow is {cw} — consider lowering to reduce cache churn")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Code usage analyzer")
    parser.add_argument("--days", type=int, default=7, help="Number of days to analyze (default: 7)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--llm", action="store_true", help="Output pre-analyzed markdown for LLM consumption")
    parser.add_argument("--project", type=str, help="Filter to specific project directory name")
    args = parser.parse_args()
    generate_report(days=args.days, project_filter=args.project, output_json=args.json, output_llm=args.llm)
