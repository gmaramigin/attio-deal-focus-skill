---
name: deal-focus-agent
description: >
  Build and run the Deal Focus Agent for an Import2 customer's Attio workspace. Every Monday morning
  the agent tells the founder which 5 deals to focus on this week, why each one matters, and what
  specific action to take, based on what was actually said in calls and emails. The agent also writes
  a health (Red/Yellow/Green) plus reasoning note onto every open deal so the whole team sees the
  same signal in their workflow. Use this skill whenever the user wants to scope, install, configure,
  or run this agent for a customer; whenever they mention "deal focus agent", "Monday digest",
  "deal health", "at-risk deals", "deal scoring", "pipeline review agent", "deal triage"; whenever
  they want to demo the agent live on a single deal; and whenever they ask how the AI implementation
  should work end to end. Trigger even if the customer name appears without the phrase "deal focus
  agent" — e.g. "run the deal agent for CLTR" or "set up the Monday digest for Acme".
---

# Deal Focus Agent

You are building or running the Import2 Deal Focus Agent on an Attio customer's workspace. The agent has one job: every Monday morning, tell the founder which 5 deals to focus on this week, why each matters, and what specific action to take — based on what was actually said in the calls and emails, not vibes.

It writes a Red / Yellow / Green health on every open deal so the team sees the same signal in their workflow. It does not replace founder judgment, does not move deals between stages, and does not email the customer's prospects. It surfaces signal so the founder spends Monday on the right deals.

## When this skill fires

Four real situations:

1. **Setup** — the user is implementing the agent for a new customer. You need to verify the Attio workspace is configured, set thresholds, pick a delivery channel, and do a dry run.
2. **Batch run** — Sunday 8pm cron fires (or the user asks to "run the Monday digest"). You score every open deal, update Attio, and deliver the top-5 digest.
3. **Demo mode** — the user is on a sales call and wants to run the agent on one specific deal live. You pull that deal's bundle, run the scoring pipeline, and return the health + reasoning + action in under 30 seconds.
4. **Scheduled run** — `/schedule` fired this prompt from cron. You are the remote Claude session that IS the runtime. No Python, no separate orchestrator. You read this SKILL.md from raw GitHub, follow Mode 2 step by step using the Attio + Gmail/Slack MCPs available to you, then deliver the digest.

Figure out which mode you're in from the user's ask, then follow the matching flow below.

## Modes

### Mode 1: Setup for a new customer

Before the agent can run, the customer's Attio needs three attributes that the MCP cannot create (see [references/attio-setup.md](references/attio-setup.md)):

1. `health` (single-select: Red / Yellow / Green) on the Deal object
2. `risk_score` (number, 0–100) on the Deal object
3. `last_analyzed_at` (date) on the Deal object

Walk the customer through creating those manually in Attio, then confirm via `list-attribute-definitions`. After that:

- Verify the workspace is Craftt via `whoami` (this is non-negotiable per the user's workspace memory).
- Identify which Attio list holds the open deals to scan.
- Capture the configuration knobs (threshold, pipelines, risk weights, delivery channel, frequency, lookback). See [references/attio-setup.md](references/attio-setup.md#configuration).
- Run Mode 3 (demo) on 3–5 deals to sanity-check the output before turning on the cron.
- Install the cron (Sunday 8pm customer's timezone by default).

### Mode 2: Monday batch run

The production loop. Steps:

1. **List open deals.** `list-records` on the customer's deals object, filter to open stages and amount above threshold (default $10k).
2. **For each deal, pull the bundle:**
   - Last 3–5 call transcripts (`semantic-search-call-recordings` + `get-call-recording`)
   - Last 5–10 emails (`search-emails-by-metadata` + `get-email-content`)
   - All notes since deal created (`semantic-search-notes` + `get-note-body`)
   - Meetings (`search-meetings`)
   - Open tasks (`list-tasks`)
   - CRM signals computed locally: days since last outbound, stage thrash count, owner-change date, champion identified yes/no
3. **Score the deal.** Send the bundle to Claude with the system prompt + signal taxonomy from [references/prompts.md](references/prompts.md). Claude returns structured JSON: `{ health, risk_score, top_signals, positive_signals, reasoning, suggested_action, stake_estimate, confidence }`.
4. **Write back to Attio:**
   - `update-record` to set `health`, `risk_score`, `last_analyzed_at`
   - `create-note` with the reasoning, 2–3 sentences citing specific calls or emails by date
5. **Rank.** `priority = risk_score × deal_amount × stage_weight` — see [references/scoring.md](references/scoring.md).
6. **Pick top 5.** Format the Monday digest per [references/digest.md](references/digest.md).
7. **Deliver.** Slack DM by default. Email or Notion page as configured.

There's a working reference runner in [scripts/run_agent.py](scripts/run_agent.py). Read it before building a customer-specific version — you'll usually fork it rather than write from scratch.

### Mode 3: Live demo (single deal)

The sales-call moment. Same per-deal pipeline as Mode 2, scoped to one deal ID. No Attio writes by default (the deal owner hasn't agreed yet). Output goes to the terminal or Slack, not into the customer's CRM.

```
deal-focus-agent demo <deal_id> --no-write
```

Speed matters. Target under 30 seconds. Use Sonnet 4.6 (not Opus) for the per-deal call, skip the full lookback window (3 most recent calls is enough for a demo), and stream the response so the founder watches it appear.

The demo moment is the close. Pick a real deal the founder knows well, run it, and let the model surface something the founder already knew but never said out loud. They'll remember it.

### Mode 4: Scheduled run (you ARE the runtime)

`/schedule` fires this prompt every Monday 8am customer-time. You are the remote Claude session. You don't call a separate Claude API — you are it. The Anthropic SDK code in `scripts/run_agent.py` is for customers who self-host on their own server; for `/schedule`, you skip that file entirely.

What you do:

1. Verify the workspace with `whoami`. Abort if it's not the customer's workspace.
2. `list-records` on the configured deals list, filter to open stages and amount above threshold.
3. For each deal, pull the bundle (calls, emails, notes, tasks, meetings) using the Attio MCP tools listed in Mode 2 step 2.
4. **You** analyze the bundle directly — read the signal taxonomy in [references/signals.md](references/signals.md), spot fired signals, cite evidence with dates. Don't invent quotes. Return your analysis as structured data in your working memory.
5. Compute risk score per the formula in [references/scoring.md](references/scoring.md). Bucket to Red/Yellow/Green.
6. Write to Attio: `update-record` for `health` + `risk_score` + `last_analyzed_at`, then `create-note` with the 2–3 sentence reasoning and the suggested action.
7. Rank by `priority = risk_score × amount × stage_weight`. Take top 5.
8. Format the digest per [references/digest.md](references/digest.md).
9. Deliver via the configured channel:
   - **Gmail draft** (default): `create_draft` to the founder's email with subject `Monday focus — <date>` and the digest as the body. The founder reads or sends.
   - **Slack DM**: `slack_send_message` to the founder's user ID.
   - **Notion page**: `notion-create-pages` titled `Monday Focus — <date>` in the customer's workspace.
10. Also print the digest as the final text of your response so it appears in the `/schedule` notification.

That's the whole flow. No separate orchestrator, no JSON parsing — you do the analysis yourself because you're already Claude.

The `/schedule` prompt template lives in the README. The placeholders (`<YOUR_WORKSPACE_NAME>`, `<DEALS_LIST_ID>`, `<THRESHOLD>`, `<FOUNDER_EMAIL>`) get filled in once when the schedule is created.

## The AI implementation

The whole thing is one Claude API call per deal. No multi-step agent loop. The orchestrator collects the bundle deterministically, hands a single rich prompt to Claude, parses the JSON back. Boring is the point — easier to debug, cheaper to run, no tool-loop tax.

Model defaults:
- **Per-deal scoring:** Sonnet 4.6. Reasoning quality matters, but each deal is a bounded analytical task — Opus is overkill.
- **Digest synthesis:** Pure code, no model call. Ranking is a formula. Formatting is a template.

Use prompt caching aggressively. The system prompt + signal taxonomy is ~3k tokens and identical across every deal in a batch. Cache it once, save ~90% on input tokens for deals 2 through N. See [references/prompts.md](references/prompts.md#prompt-caching) for the exact `cache_control` setup.

Structured output: ask for JSON, validate with a schema, retry once on parse failure. Keep the schema flat — health, risk_score, top_signals (array of {signal, evidence}), reasoning, suggested_action, stake_estimate, confidence. Detail in [references/prompts.md](references/prompts.md#output-schema).

## Reference files

Read these as needed. They exist so SKILL.md stays readable and the depth is one click away.

| File | Read when |
|------|-----------|
| [references/signals.md](references/signals.md) | Tuning the signal taxonomy for a customer, or debugging "why did this deal score yellow?" |
| [references/prompts.md](references/prompts.md) | Implementing the Claude API call, adjusting prompts, or changing model/caching |
| [references/scoring.md](references/scoring.md) | Tuning the risk formula or top-5 selection logic |
| [references/digest.md](references/digest.md) | Changing the digest format, delivery channel, or example template |
| [references/attio-setup.md](references/attio-setup.md) | Onboarding a new customer or hitting an Attio MCP limit |

## Hard rules

These mirror the customer-facing scope. Don't quietly cross them.

- **Never email the customer's prospects.** Outbound is the customer's job. Out of scope.
- **Never move a deal between stages.** That's hygiene-agent territory.
- **Never grade individual rep performance.** Politically explosive. The output ranks deals, not people.
- **Never touch deals below the threshold.** Keeps cost and attention focused.
- **Never write to Attio in demo mode by default** — the deal owner hasn't signed off yet.
- **Never invent a quote or signal.** Every claim in the reasoning must cite a real call date, email date, or note. If the bundle is empty, say so and score `unknown` rather than guess.

## Cost expectation

At default settings (deals above $10k, 3–5 calls + 5–10 emails per deal, ~50 open deals per customer, Sonnet 4.6 with caching), tokens run roughly $10–30/month per customer. Surface this to the customer when they ask — the retainer is $400–700/mo, the tokens are tiny by comparison.
