# Claude API Implementation

The agent makes one Claude API call per open deal. No tool use, no agent loop, no chain of thought beyond what the model needs internally. The orchestrator does the data collection; Claude does the analysis.

## Model selection

| Mode | Model | Why |
|------|-------|-----|
| Batch per-deal scoring | `claude-sonnet-4-6` | Best ratio of reasoning to cost for this bounded task. ~50 deals × 10k input tokens × $3/Mtok = ~$1.50/run before caching. With caching ~$0.30. |
| Live demo | `claude-sonnet-4-6` | Same model, smaller bundle (3 calls instead of 5, no notes lookback) for speed. |
| Don't use | `claude-opus-4-7` | Overkill. Per-deal analysis isn't reasoning-bound, it's signal-recognition bound. |
| Don't use | `claude-haiku-4-5-20251001` | Reasoning isn't strong enough to cite evidence reliably. We tried — the model invents quotes. |

If a customer has a small pipeline (<15 open deals), Opus is fine and only adds ~$2/month — but the quality lift is marginal. Default to Sonnet.

## Prompt caching

The system prompt + signal taxonomy is the same across every deal in a batch. Cache it.

```python
system=[
    {
        "type": "text",
        "text": SYSTEM_PROMPT,  # see below, ~3k tokens
        "cache_control": {"type": "ephemeral"}
    }
]
```

First deal in the batch writes the cache (10% premium on input tokens). Deals 2 through N read the cache (90% discount on the cached portion). At 50 deals, this saves roughly 80% of input token cost.

The cache TTL is 5 minutes by default. Run the batch sequentially or in tight parallel; don't let a deal slip 5+ minutes after the cache write.

If you want longer caching for very large pipelines, set `"cache_control": {"type": "ephemeral", "ttl": "1h"}` — but you pay a higher write cost, so it only wins above ~30 cached reads in the hour.

## The system prompt

This is the cached prefix. Tune for the customer's tone and signal weights, but keep the structure.

```
You are the Deal Focus Agent for {customer_name}'s sales pipeline. You analyze
one deal at a time and return a structured assessment that helps the founder
decide which deals to focus on this week.

# Your job

For each deal, you read:
- Recent call transcripts (the last 3–5)
- Recent emails (the last 5–10)
- Notes the team has written
- Open tasks
- CRM activity facts (last outbound, stage history, owner changes, champion status)

You return ONE JSON object matching the output schema. You never make up
quotes or signals. Every signal you fire must cite a specific call date,
email date, or note. If the bundle is empty or you can't find evidence
for any signal, return `confidence: 0` and stop.

# What you look for

Risk signals — conversations:
- pricing_pushback_unresolved: pricing concern raised >1x and never addressed
- decision_maker_pulling_away: DM attended early calls, skipped recent ones
- competitor_positive_mention: buyer mentions a competitor in positive framing
- timeline_slipping_no_date: "circle back next quarter" with no committed date
- internal_blocker_named: procurement/legal/manager blocker unresolved
- vague_next_step: last call ended without a committed next step
- champion_losing_energy: champion participating less over time

Risk signals — CRM activity (provided to you as facts):
- no_outbound_owner
- generic_check_in_last_touch
- stage_thrashing
- owner_changed_recently
- no_champion_identified

Risk signals — emails:
- response_time_degrading: buyer's reply latency grew >2x vs early deal
- manager_cc_silence: senior person CC'd then never replied
- repeated_hedging: hedging language used 2+ times

Positive signals (reduce risk):
- specific_implementation_question: SSO, migration, API, rollout questions
- multiple_stakeholders_engaged: multiple buyer-side people actively contributing
- we_when_we_deploy_language: mental ownership
- asking_about_terms: pricing tiers, contract length, references, MSA

# How you reason

1. Read the bundle.
2. List every signal that fires, with evidence (date + quote or paraphrase).
3. List every positive signal that fires, same format.
4. Draft a 2–3 sentence reasoning that the founder will read in a Slack DM.
   Cite specific dates. Be concrete. No corporate language.
5. Propose a specific next action this week — not "follow up", but "send
   Sarah the SOC 2 doc and propose a Pradeep walkthrough Tuesday."
6. Estimate the dollar stake. Usually equals deal amount, but if the deal
   has obvious expansion potential mentioned in the calls, surface that too.
7. Set confidence based on bundle richness. <0.4 means "I don't have enough
   data to score this honestly."

# Constraints

- No invented quotes. If you can't cite it, you didn't see it.
- No grading the rep. The output ranks deals, never people.
- No commentary on whether the customer should buy or not. You score
  health, not desirability.
- Reasoning must fit a Slack message — 2–3 sentences, plain language,
  no headers, no bullets in the reasoning field.
- The suggested_action must be a single concrete step. Not a plan, not
  a list. One thing to do this week.
```

## The per-deal user message

This is the part that changes for each deal. Bundle the inputs into one structured user message.

```python
user = {
    "role": "user",
    "content": [
        {
            "type": "text",
            "text": f"""
Deal: {deal_name}
Amount: ${deal_amount:,}
Stage: {stage}
Owner: {owner_name}
Days in current stage: {days_in_stage}
Days since deal created: {days_since_created}

# CRM activity facts
Last outbound from owner: {last_outbound_date} ({last_outbound_days_ago} days ago)
Last outbound was generic check-in: {is_generic_check_in}
Stage transitions in last 30 days: {stage_transitions}
Owner changed in last 30 days: {owner_changed} (previous: {previous_owner})
Champion identified: {has_champion} ({champion_name or 'none'})

# Calls
{call_transcripts_formatted}

# Emails
{emails_formatted}

# Notes
{notes_formatted}

# Open tasks
{tasks_formatted}

Return one JSON object matching the schema. No prose outside the JSON.
"""
        }
    ]
}
```

Format calls and emails with clear delimiters and dates. Truncate individual call transcripts to ~2000 tokens (keep the opening, the discussion of pain/price/timeline, and the close). Emails can stay full length usually — they're short.

## Output schema

The model returns JSON. Validate with a Pydantic schema or equivalent. Retry once on parse failure with a "your previous response was invalid JSON, return only the JSON object" reminder.

```json
{
  "deal_id": "string",
  "health": "red | yellow | green | unknown",
  "risk_score": 0-100,
  "top_signals": [
    {"signal": "signal_name", "evidence": "specific quote + source date"}
  ],
  "positive_signals": [
    {"signal": "signal_name", "evidence": "specific quote + source date"}
  ],
  "reasoning": "2-3 sentences for the digest, cites dates",
  "suggested_action": "One specific step for this week",
  "stake_estimate": {
    "amount": 0,
    "currency": "USD",
    "expansion_note": "optional sentence about likely expansion"
  },
  "confidence": 0.0-1.0
}
```

The orchestrator owns final scoring math. Even though Claude returns `risk_score`, the orchestrator recomputes it from the signals and weights — that way risk math is deterministic and tunable without prompt edits. The model's `risk_score` is a sanity check, not the source of truth.

## Anthropic SDK call shape

```python
from anthropic import Anthropic

client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[user_message]
)

raw = response.content[0].text
result = parse_json_with_retry(raw, client, user_message)
```

Watch the response object for cache hit telemetry:
```python
response.usage.cache_creation_input_tokens  # >0 on first call of batch
response.usage.cache_read_input_tokens       # >0 on subsequent calls
```

Log these. If cache reads are 0 on deal 2+, something killed your cache (TTL expired, prompt drifted, or you forgot the `cache_control` block) and your batch is paying full freight.

## Live demo tuning

For demo mode, optimize for speed and drama:

- Cut the bundle to 3 most recent calls + 5 most recent emails.
- Stream the response (`stream=True`) so the founder watches the analysis appear.
- Print the reasoning first, suggested_action second. The founder cares about why and what to do, not the score in isolation.
- Don't write to Attio. The deal owner hasn't agreed yet.

A clean demo runs in 20–30 seconds. If you're over 60 seconds, your bundle is too big.

## Failure modes to expect

- **Model returns invalid JSON.** Retry once with a "JSON only" reminder. If it fails twice, log and skip the deal — don't crash the batch.
- **Model invents a quote.** This is the worst failure because it erodes trust. Mitigate by: (1) explicit instruction in the system prompt, (2) post-hoc validation — for each signal's evidence, check that the quoted substring actually appears in the bundle. Flag mismatches; don't deliver them.
- **Cache miss on every deal.** Usually means the system prompt is being templated per deal (e.g., customer name interpolated). Move per-deal content into the user message; keep the system prompt byte-identical across the batch.
- **Bundle too large.** If a deal has 30 calls and 100 emails, you'll blow context. Cap at the lookback window (default 30 days) and the per-stream limits (3–5 calls, 5–10 emails, all notes since deal created).
