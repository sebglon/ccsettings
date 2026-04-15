---
name: usage-report
description: >
  Weekly Claude Code token usage and cost analysis. Run with /usage-report to analyze
  the last 7 days of sessions, identify cost drivers (long sessions, subagent overhead,
  skill bloat), and get actionable recommendations to reduce token spend.
  Use when user asks about "usage", "tokens", "cost", "spending", "reduce cost",
  "analyze sessions", or invokes /usage-report.
---

# Claude Code Usage Report Skill

Run the usage analysis script and present findings with recommendations.

## Steps

1. Run the analysis script with `--llm` for pre-analyzed output:
```bash
python3 ~/.claude/scripts/claude-usage-report.py --days 7 --llm
```
   Adjust `--days N` if the user specifies a different period.

2. The `--llm` output already includes:
   - Current settings context (model, autoCompactWindow)
   - Cost breakdown with percentages and primary cost driver
   - Daily trends table
   - Top sessions ranked by **full cost** (including cache, not just input+output)
   - Session durations and per-session cost driver
   - Pre-computed analysis (session length impact, model usage, tool efficiency, skill overhead)

3. Based on the report, provide **actionable recommendations** specific to the data:
   - Cite exact numbers from the report (e.g., "10 long sessions = 89% of cost")
   - Suggest concrete settings changes with current vs. proposed values
   - Prioritize by impact (cost % saved)

4. If the user wants to apply changes, help them edit `~/.claude/settings.json` directly.

5. Other output modes:
   - `--json` for raw JSON (programmatic use)
   - No flag for human-readable terminal output

6. Pricing is hardcoded in the script — if costs look off, verify against https://docs.anthropic.com/en/docs/about-claude/models and update `PRICING` dict.
