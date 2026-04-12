# Claude Code Settings & Skills

Personal Claude Code configuration and custom skills.

## Installation

```bash
# Clone this repo
git clone https://github.com/sebglon/ccsettings.git ~/git-repo/ccsettings
cd ~/git-repo/ccsettings

# Symlink global CLAUDE.md into ~/.claude/
ln -s "$(pwd)/CLAUDE.md" ~/.claude/CLAUDE.md

# Symlink skills into ~/.claude/skills/
ln -s "$(pwd)/skills/usage-report" ~/.claude/skills/usage-report

# Symlink scripts into ~/.claude/scripts/
mkdir -p ~/.claude/scripts
ln -s "$(pwd)/scripts/claude-usage-report.py" ~/.claude/scripts/claude-usage-report.py
```

> **Note:** `~/.claude/CLAUDE.md` is the user-level Claude Code config loaded in every project.
> Symlinking it here keeps your global preferences version-controlled in this repo.

## Structure

```
├── CLAUDE.md              # Global Claude Code config (symlinked to ~/.claude/CLAUDE.md)
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
