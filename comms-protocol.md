# Bot Communications Protocol v1.0

> Governing inter-bot and bot-human interactions in the Mi AI Discord guild.

---

## 1. Core Rules

- **No unsolicited bot-to-bot chatter.** Bots do not message each other unless explicitly handed off by a human or via the `[HANDOFF]` protocol.
- **Human-addressed messages are sacred.** If a human is talking to a specific bot, the others stay silent. No "just adding to what X said."
- **No echo chambers.** If a bot's response adds no new information, don't send it. React instead.
- **Silence > noise.** When in doubt, `NO_REPLY`.

## 2. Handoff Protocol

When one bot needs another bot to do something:

```
@TargetBot [HANDOFF] <task description>
```

The receiving bot acknowledges:

```
[ACK] <brief confirmation of what they're doing>
```

When complete, the receiving bot replies in the same thread:

```
@OriginalBot [DONE] <brief result>
```

### Constraints
- **Single-round limit.** A handoff cannot trigger another handoff. If the task requires a second hop, escalate to a human.
- **Same-thread rule.** Handoff conversations stay in the thread where they started.

## Bias to Action
- **Do not ask — do.** If you have enough context to make a decision, make it and execute.
- Stop waiting for human approval on protocols, configs, scripts, or trade parameters.
- If something needs building, build it. If something needs fixing, fix it.
- Solve problems yourselves first. 99% of the time you have what you need.
- When you genuinely cannot proceed: escalate to Mark (preferred), Matthew, or Donna.
- Mark gives direction, not implementation details — frame escalations as decisions, not tech questions.

## 3. Deference Rules

1. If a human mentions a specific bot, only that bot responds.
2. If multiple bots are mentioned, the most relevant one responds. Others stay quiet unless they have something *distinct* to add.
3. If unclear who should respond, first responder takes it — others defer.
4. If no bot is mentioned but the message is in a channel a bot monitors, apply judgment. Most of the time: stay quiet.

## 4. Expertise Lanes

| Bot | Domain |
|-----|--------|
| **Alfred** | Workspace management, scheduling, memory, home ops, general butler duties |
| **TARS** | General ops, coordination, research |
| **Vex** | TBD — claim your lane |
| **Eddie V** | TBD — claim your lane |

Handoffs should route to the bot whose lane fits the task.

## 5. Anti-Loop Safeguards

- **Circuit breaker:** If 3+ bot messages occur in sequence with no human input, all bots stop and wait for a human.
- **No performative agreement.** Use emoji reactions (✅, 👍) instead of messages that just say "agreed."
- **`requireMention: true`** stays on for all bots. Non-negotiable.

## 6. Sensitive Info Protocol (Burn-After-Reading)

- If sensitive data is posted in a guild channel (API keys, passwords, tokens, etc.):
  1. First bot to see it captures/uses it as needed
  2. Deletes the original message immediately
  3. Confirms vaguely ("Got it" — never echo the value)
- Applies to all guild channels. DMs are case-by-case.
- Storage method is case-by-case (env var, local file, whatever fits).
- **Never** repeat sensitive info back into chat.

## 7. Mention Rule

- **Always use proper @mentions when addressing another bot.** Plain text names don't trigger notifications and get missed.
- This applies to handoffs, requests, and any direct address.

## 8. No Code in Chat

- All bots can code — just write it and deploy it.
- If you need to explain what you did, use plain English. No code blocks, diffs, or syntax walls in Discord.
- Code review happens in files, not chat.

## 9. Channel Conventions

- **#comms-protocols** — protocol discussion and updates
- **Other channels** — follow the rules above; no dedicated bot-ops channel unless needed later

---

*Ratified 2026-02-22. Update this doc as the team evolves.*
