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

1. Run the analysis script:
```bash
python3 ~/.claude/scripts/claude-usage-report.py --days 7
```

2. If the user asks for JSON output or deeper analysis:
```bash
python3 ~/.claude/scripts/claude-usage-report.py --days 7 --json
```

3. After showing the report, provide **actionable recommendations** based on the data:

### Common optimizations to suggest:

**If cache read > 100M tokens:**
- Lower `autoCompactWindow` in `~/.claude/settings.json` (e.g., from 500K to 200K)
- Start fresh sessions instead of marathon conversations
- Use `/clear` to reset context when switching topics

**If subagent overhead > 30%:**
- Use direct tool calls (Read, Grep, Glob) instead of Agent for simple lookups
- Reduce code-reviewer agent frequency — only at major milestones
- Avoid Agent for tasks that need < 3 tool calls

**If skill invocations are high:**
- Each Skill invocation injects a large prompt into context
- Brainstorming/planning skills are useful but expensive — use for complex tasks only
- Consider if the superpowers plugin is adding value proportional to its cost

**If sessions are very long (>200 messages):**
- Break work into focused sessions
- Commit and start fresh when switching tasks
- Use `/compact` to manually compress context mid-session

4. If the user wants to apply changes, help them edit `~/.claude/settings.json` directly.

5. Remind the user to run this weekly: `/usage-report`
