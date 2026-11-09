# One real AI draft, checked

This folder holds one summary drafted by Claude for the messy sample (`data/sample`) and the verdict the verifier gave it.

- Date: 2026-11-09.
- Model: `claude-sonnet-5-5`, as reported by the Claude Code CLI.
- Prompt: the engine's own. `PROMPT + _facts(results)` from `engine/summarize.py`, built from the sample's results and sent as the user message.
- How it was sent: through the Claude Code CLI on a subscription, not through the API path in `summarize.py`. The engine has no system prompt, so the CLI got one neutral line.
- Command, run from an empty directory outside any project:
  `claude -p --model sonnet --system-prompt "You are a careful writing assistant." --tools "" --setting-sources "" --disable-slash-commands --strict-mcp-config --no-session-persistence --output-format json < prompt.txt`
- Draft: `draft.txt`, the model's reply as received. Only the surrounding whitespace is trimmed, as `draft()` does.
- Verdict: `verdict.txt`. The verifier PASSED it: five sentences, each citing its analysis once, every number equal to a computed figure, and the not-computed items described as not computed.
- One thing the verifier does not catch: the prompt said "no dates", and the draft names the months 2025-01, 2025-03, 2025-04, 2025-05 and 2025-06. The verifier treats a month label as a date, not a number, and checks values and units, not wording.

`tests/test_verify_pipeline.py::test_committed_ai_draft_gets_its_committed_verdict` re-runs the verifier on `draft.txt` and fails if the verdict changes. The template is still the default drafter, and the committed reports use it.
