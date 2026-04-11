# Claude Code Settings & Skills

Personal Claude Code configuration and custom skills.

## Installation

```bash
# Clone this repo
git clone https://github.com/sebglon/ccsettings.git

# Symlink skills into ~/.claude/skills/
ln -s "$(pwd)/ccsettings/skills/usage-report" ~/.claude/skills/usage-report

# Symlink scripts into ~/.claude/scripts/
ln -s "$(pwd)/ccsettings/scripts/claude-usage-report.py" ~/.claude/scripts/claude-usage-report.py
```

## Structure

```
├── settings.json          # Claude Code settings (reference)
├── skills/
│   └── usage-report/      # Weekly token usage & cost analysis skill
│       └── SKILL.md
└── scripts/
    └── claude-usage-report.py  # Usage report analyzer script
```

## Skills

### usage-report

Weekly Claude Code token usage and cost analysis. Invoke with `/usage-report`.

Analyzes the last 7 days of sessions, identifies cost drivers (long sessions, subagent overhead, skill bloat), and provides actionable recommendations.
