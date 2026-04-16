## Approach

- Think before acting. Read existing file before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read file you have already read unless the file may have changed.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solution simple and direct.
- User instructions always override this file.
- Respond in English unless asked otherwise.

## Token Efficiency

**Model selection — use the right model for the task:**
- Subagents: use `model: "sonnet"` by default. Use Opus only for architecture decisions, complex debugging (>5 files), or security review.
- Main conversation: Opus is fine for complex work (specs, architecture, multi-file refactors). Use /fast (Sonnet) for routine tasks (simple edits, lookups, test fixes).
- Don't overthink model choice — quality matters more than marginal token savings.

**Direct tools over agents:**
- Use Read, Grep, Glob directly instead of spawning Agent for simple lookups (< 3 tool calls).
- Never use Agent:Explore when a single Grep or Glob suffices.
- Max 1 code-reviewer per completed feature, never mid-development.

**Session hygiene (biggest cost lever):**
- Suggest starting a fresh session after ~150 messages or when switching to a different task.
- Long sessions (>200 messages) cause exponential cache read costs.

**Skills:**
- Use brainstorming/writing-plans for multi-step tasks (>3 files) — they improve quality.
- Skip them for trivial changes, but don't avoid them when they'd genuinely help.

## Workflow

- **Worktrees are mandatory**: for every plan or implementation task, use an isolated git worktree before starting any code.
