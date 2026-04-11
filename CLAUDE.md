## Approach

- Think before acting. Read existing file before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read file you have already read unless the file may have changed.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solution simple and direct.
- User instructions always override this file.
- Respond in French unless asked otherwise.

## Token Efficiency

- Use Read, Grep, Glob directly instead of spawning Agent for simple lookups (< 3 tool calls).
- Never use Agent:Explore when a single Grep or Glob suffices.
- Only use brainstorming/planning skills for complex multi-step tasks, not small fixes or edits.
- Skip code-reviewer agent unless explicitly asked or at a major milestone.
- When answering questions, give the answer first — no preamble, no restating the question.

## Workflow

- **Worktrees obligatoires** : pour chaque plan ou tâche d'implémentation, utiliser un git worktree isolé (skill `superpowers:using-git-worktrees`) avant de commencer le code.
- **Subagents Haiku** : utiliser `model: "haiku"` sur les Agent pour les tâches mécaniques (boilerplate, tests unitaires, config).
