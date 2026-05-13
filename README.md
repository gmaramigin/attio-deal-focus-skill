# deal-focus-agent

A Claude Code skill that tells the founder which 5 deals to focus on this week, why each one matters, and what specific action to take. Reads calls, emails, and notes from your Attio workspace. Updates a Red/Yellow/Green health on every open deal. Delivers a Monday digest to a Slack channel. Runs on a weekly cron in your own account.

## What it does

Every Monday morning you get one screen:

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

The skill also writes a `health` (Red/Yellow/Green) + reasoning note onto every open deal in Attio so your team sees the same signal in their workflow.

## Why it runs on your own account

You own the Anthropic key, the Attio connector, and the schedule. Your tokens, your CRM, your control. If your consultant disappears, the skill keeps running. Token cost runs roughly $10–30/month at typical volume.

## What it does NOT do

- Does not email your prospects. Outbound is your job.
- Does not move deals between stages. That's the pipeline-hygiene agent.
- Does not grade individual reps. Ranks deals, never people.
- Does not touch deals below the threshold.

## Prerequisites

- [Claude Code](https://claude.com/claude-code) installed and signed in
- An Attio workspace with admin access
- The [Attio MCP connector](https://attio.com/help/articles/4544827) connected to Claude Code
- The [Slack connector](https://claude.ai/settings/connectors) connected to Claude Code (default delivery) — or Gmail / Notion as alternatives
- A Deal object with `stage`, `amount`, and `owner` attributes (Attio defaults work)
- Three custom attributes on the Deal object — you create these in Attio first (see Setup step 1)

## Setup

### 1. Create the health attributes in Attio

The Attio MCP cannot create attributes, so you do this once in the Attio UI:

Settings → Objects → Deal → Attributes → Add attribute:

| Attribute | Type | Values |
|-----------|------|--------|
| `health` | Single-select | Red, Yellow, Green, Unknown |
| `risk_score` | Number | 0–100, no decimals |
| `last_analyzed_at` | Date | — |

### 2. Identify your open deals list

In Attio, find or create a list filtered to non-closed stages. Note the list ID — you'll see it in the URL like `app.attio.com/.../list/abc123def`.

If you don't have a list yet: Lists → New list → filter by `stage is not Closed-Won, Closed-Lost` → sort by `amount` desc.

### 3. Install the skill

```bash
git clone https://github.com/gmaramigin/attio-deal-focus-skill.git
mkdir -p ~/.claude/skills/deal-focus-agent
cp -r attio-deal-focus-skill/SKILL.md attio-deal-focus-skill/references attio-deal-focus-skill/scripts ~/.claude/skills/deal-focus-agent/
```

Or, if you don't want local install and want to run only via `/schedule`, skip this step entirely — the schedule prompt fetches the skill from raw GitHub.

### 4. Run a dry test

In Claude Code:

> Run the deal-focus-agent in demo mode on one of my open deals. Pick the highest-value deal in negotiation. Do not write to Attio.

Walk through the output. Check that the reasoning cites real calls and emails. Tune the signal weights in `references/signals.md` if anything scored wrong.

## Usage

### On demand

In any Claude Code session:

> Run the deal-focus-agent on my Attio. Email me the top 5.

> Score every open deal above $10k and update health in Attio.

The skill triggers on phrases like "deal focus agent", "Monday digest", "score my deals", "which deals should I focus on", "at-risk deals".

### Weekly cron via /schedule (recommended)

In Claude Code:

```
/schedule
```

Then paste this when prompted:

```
Cadence: 0 8 * * 1 (Mondays 8am, in your local timezone)
Name: deal-focus-monday
MCP: Attio, Slack

Prompt:
You are running the Monday deal-focus-agent pass over the <YOUR_WORKSPACE_NAME> Attio workspace.

Fetch the playbook from https://raw.githubusercontent.com/gmaramigin/attio-deal-focus-skill/main/SKILL.md and follow Mode 4 (Scheduled run) exactly. Fetch references/signals.md, references/scoring.md, references/digest.md as needed from the same repo.

Configuration:
- Deals list ID: <DEALS_LIST_ID>
- Threshold amount: $<THRESHOLD>          # ignore deals under this
- Lookback days: 30
- Slack channel for the digest: <SLACK_CHANNEL>   # e.g. #general or #deal-focus
- Workspace expected from whoami: <YOUR_WORKSPACE_NAME>

At the end:
1. Confirm every open deal got a Red/Yellow/Green health written to Attio plus a reasoning note.
2. Send the full digest to the Slack channel <SLACK_CHANNEL> via slack_send_message. Use Slack markdown for formatting (emoji as Unicode, *bold*, blank lines between entries).
3. Print the full digest as your final response so it appears in the schedule notification.

Constraints (hard):
- Never invent quotes. Every cited fact must trace to a real call date, email date, or note.
- Never write to Attio if whoami returns a workspace other than <YOUR_WORKSPACE_NAME>.
- Never email or DM customer prospects. Outbound is the founder's job.
- Never grade rep performance.

If anything fails, stop and report the exact error.
```

Replace the `<PLACEHOLDERS>` with your values before submitting:

| Placeholder | Replace with |
|---|---|
| `<YOUR_WORKSPACE_NAME>` | Exact value `whoami` returns from the Attio MCP |
| `<DEALS_LIST_ID>` | The list ID from Attio (URL fragment after `/list/`) |
| `<THRESHOLD>` | Dollar amount below which deals are ignored (default `10000`) |
| `<SLACK_CHANNEL>` | Channel name with `#` prefix (default `#general`). For customers with revenue-sensitive teams, use a private channel like `#deal-focus` or `#sales-leadership`. |

### Where the digest lands

By default, two places:

1. **Slack channel `#general`** (or whatever you set `<SLACK_CHANNEL>` to) — the digest posts Monday morning. The team sees the same signal in the same place. No member IDs to copy, no per-person config.
2. **The `/schedule` notification** in Claude Code — when you open Claude Monday morning, the digest is also in the notification stream.

To send to a Slack DM instead of a channel: in the prompt above, replace `<SLACK_CHANNEL>` with your Slack user ID (`U01234567`). The `slack_send_message` tool routes a `U...` recipient as a DM.

To swap Slack for Gmail draft: in the prompt above, replace step 2 with `Create a Gmail draft to <FOUNDER_EMAIL> with subject "Monday focus — <today's date>" and the digest as the body.` and swap `Slack` for `Gmail` in the MCP list.

To swap for Notion: replace step 2 with `Create a Notion page titled "Monday Focus — <date>" in the <NOTION_PARENT_PAGE_ID> page with the digest as the body.` and swap `Slack` for `Notion` in the MCP list.

## Verifying it works

After the first run:

1. Open Attio → any open deal → check the `health` attribute is set and a fresh note is attached titled with today's date.
2. Open Slack → the configured channel → confirm the digest posted Monday morning.
3. Click through 2–3 random deals and confirm the reasoning cites actual calls/emails from the lookback window. If it cites something that's not in the deal's record, that's a bug — open an issue.

## Customizing

### Signal weights

Open `references/signals.md`. Each signal has a default weight. Adjust per customer based on what they actually care about. Re-run the dry test after each change.

### Stage weights

Open `references/scoring.md`. Adjust the stage weight table to match your Attio stage names. Deals closer to a decision should have higher weight.

### Bucket thresholds

Default: Yellow at risk ≥ 30, Red at risk ≥ 60. Adjust in the schedule prompt if you want stricter or looser flags.

### Top-N

Default is top 5. Change in the schedule prompt if you want top 3 or top 10.

## Troubleshooting

**"Skill not triggering on demand"** — `SKILL.md` must live at `~/.claude/skills/deal-focus-agent/SKILL.md` along with the `references/` and `scripts/` directories. Restart Claude Code after install.

**"Workspace mismatch" errors** — The skill aborts if `whoami` returns a different workspace. Fix the placeholder or switch your Attio MCP to the right workspace.

**"Schedule fires but no Slack message arrives"** — Three things to check: (1) Slack MCP is connected to the schedule's MCP list. (2) `<SLACK_CHANNEL>` is a channel the connected Slack app can post to — for a private channel, the app must be invited (`/invite @Claude` in that channel). (3) Channel name format includes the `#` prefix (e.g. `#general`, not `general`).

**"Digest reasoning is generic"** — Bundle is too thin. Either no recent calls/emails are linked to the deal, or the lookback window is too short. Check the deal in Attio → activity tab. If activity is sparse, the agent honestly says so and scores `unknown`.

**"Same deals flagged every week with no change"** — Working as designed: the freshness rule keeps last week's deals visible until you act on them. If you act and the digest still flags it, your action didn't generate new outbound from the owner. The agent looks for new activity, not new intent.

**"Phantom risk score on a deal with no data"** — Confidence gate isn't firing. Lower the confidence threshold or surface the bundle size in the digest so you can spot phantoms.

## How it's built

The full skill design lives in `SKILL.md`. The signal taxonomy, prompts, scoring math, and digest format live in `references/`. A reference Python runner for self-hosted execution lives in `scripts/run_agent.py` — most people don't need it; `/schedule` is enough.

This is the production form of "Agent 2: Deal focus" from the Import2 Attio AI agents lineup. The sibling is [attio-pipeline-hygiene-skill](https://github.com/gmaramigin/attio-pipeline-hygiene-skill) which cleans the room. This one tells you where to focus.

## License

MIT. Fork it, adapt it, ship it.
