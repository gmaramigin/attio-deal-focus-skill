# Digest Output

The Monday digest is the founder-facing output. One screen, one decision, one action per deal. The rest of the system exists to make this digest worth reading.

## Format — the canonical entry

Each top-5 entry follows this exact structure. Don't add headers, sections, or bullets the founder didn't ask for.

```
{health_emoji} {deal_name} — ${amount:,} — {stage_status}

Why: {reasoning, 1-2 sentences citing actual calls or emails with dates}

Do this week: {suggested_action, specific and concrete}

Stake: ${stake_amount} now{ + likely ${expansion_amount} {expansion_timing} if expansion_note}
```

### Health emojis

| Health | Emoji |
|--------|-------|
| Red | 🔴 |
| Yellow | 🟡 |
| Green | 🟢 |
| Unknown | ⚪ |

The emoji is the first thing the founder sees in the Slack DM. Color carries.

### Stage status string

Concise context about where the deal is and how long it's been there. Examples:

- "stuck 18 days in Proposal"
- "Negotiation, 5 days"
- "Contract sent, 12 days no response"

Compute it as `{stage}, {days_in_stage} days` and add the "stuck" prefix if `days_in_stage > 2 × median_stage_duration` for that customer.

## The full digest

```
{greeting_line}

{n} deals to focus on this week. {high_level_summary}

{entry_1}

{entry_2}

{entry_3}

{entry_4}

{entry_5}

{footer_line}
```

### Greeting line

Keep this minimal. The founder isn't reading it for warmth.

Good: `Monday focus, {date}.`
Bad: `Good morning! Hope you had a great weekend!`

### High-level summary

One sentence that contextualizes the week. Examples:

- "3 reds, 2 yellows. $185k at stake."
- "Pipeline cleaner this week — only one red. Other 4 are nudges, not fires."
- "Heavy week. 4 reds. Most have specific actions you can take today."

Compute the dollar total from `stake_estimate.amount` across the top 5.

### Footer line

A pointer to where the full Attio data lives, plus a "reply with feedback" invite for the retainer relationship.

```
Full deal health updated in Attio. Reply if any of these scored wrong — helps tune next week.
```

## Worked example

This is the canonical example the user gave in the spec. Match this voice across customers.

```
Monday focus, June 12.

3 reds, 2 yellows. $185k at stake.

🔴 Globex Inc. — $45,000 — stuck 18 days in Proposal

Why: In your June 3 call with their CTO Sarah Chen, she raised implementation
concerns three times: pricing, security, onboarding timeline. None appear
addressed in the four follow-up emails. Her manager Pradeep was CC'd on
June 7 but hasn't replied. Last outbound was a generic check-in on June 10.

Do this week: Send Sarah a specific SOC 2 doc and propose a 30-minute call
with Pradeep to walk through procurement timeline. Reference her June 3
concern about audit logs.

Stake: $45k now + likely $80k expansion in Q4.

🔴 ...
```

Notice what's there: specific dates, specific names, specific actions. Notice what's not there: jargon, hedging, multiple recommendations per deal.

## Delivery channels

### Slack DM (default)

Use the Slack MCP `slack_send_message` against the founder's user ID. Format with Slack markdown — emoji as Unicode, bold via `*text*`, code blocks for nothing. Slack renders the format above naturally.

Send to the founder's DM, never to a channel. The digest names deals and amounts; that's not channel content.

If the customer has a paid Slack and wants the digest threaded to a private "deal-review" channel, set that in the config. Same content, different recipient.

### Email

Use the Gmail MCP or the customer's own SMTP. Subject line:

```
Monday focus — {n} deals — ${total_stake:,} at stake
```

Body: same format as Slack, but use HTML so emojis render cleanly and the digest stays scannable on mobile. No images, no tracking pixels, no marketing chrome.

### Notion page

Use the Notion MCP to create or update a page in the customer's workspace. Title: `Monday Focus — {date}`. Body: same content, formatted as Notion blocks. Replace the prior week's page or append, per the customer's preference.

### Attio note only

Lightest-touch delivery. Create one note attached to a "Monday Focus" meta record in Attio with the full digest content. No external delivery. Useful for customers who don't want to be pinged and prefer to find it themselves in the CRM.

## The Attio per-deal note

Separate from the digest. Every open deal gets a fresh note each Monday with:

```
Health: {Red/Yellow/Green} (risk_score: {n})

{reasoning, 2-3 sentences}

Suggested action: {suggested_action}

— Deal Focus Agent, {date}
```

Use `create-note` against the deal record. Don't update the prior note; append a new one each Monday so the deal has a visible health timeline.

If a deal moved from Red to Yellow week-over-week, prepend a one-line celebration:

```
↑ Improved from Red last Monday.
```

That's the kind of micro-feedback that makes the team trust the agent.

## Tone rules

- **Cite, don't summarize.** "In your June 3 call, Sarah said X" beats "the customer has concerns."
- **One action, not a plan.** "Send the SOC 2 doc" beats "Address the security concerns by preparing materials and scheduling a follow-up."
- **No corporate language.** "Procurement pushback" not "alignment headwinds." The founder isn't reading consulting prose.
- **No em dashes.** (Per the user's writing style memory.) Use periods or commas instead.
- **No "we" or "you should".** The founder is the actor. State the action directly.
- **No padding.** If the bundle is thin, say so honestly. Don't fill with vibes.

## What the digest does NOT include

- Rep-level stats. No "Sarah closed 3 deals last quarter."
- Pipeline coverage math. No "you're at 2.3x of quota."
- Deals below the threshold. No noise from the long tail.
- Generic advice. No "consider building rapport with the manager."
- Self-promotion. The agent doesn't congratulate itself or remind the founder that it's working.
