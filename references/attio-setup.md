# Attio Setup

Before the agent can run on a customer's workspace, three attributes have to exist on the Deal object. The Attio MCP cannot create attributes — you walk the customer (or yourself, if you have expert access) through creating them in the Attio UI.

## Required attributes on the Deal object

| Attribute | Type | Values | Why |
|-----------|------|--------|-----|
| `health` | Single-select | Red, Yellow, Green, Unknown | The headline signal. Visible on every deal record so the team sees what the founder sees. |
| `risk_score` | Number | 0–100 | The numeric backing the color. Lets the team filter or sort. |
| `last_analyzed_at` | Date | — | Detects stale scores. If a deal hasn't been analyzed in N days, the orchestrator knows. |

### How to create them in Attio

1. Go to Settings → Objects → Deal → Attributes.
2. Click "Add attribute" for each one.
3. For `health` (Single select), add the four options. Set color hints if the customer wants (red/yellow/green/gray).
4. For `risk_score` (Number), set min 0, max 100, no decimals.
5. For `last_analyzed_at` (Date), no extra config.

Confirm via the MCP after creation:

```
list-attribute-definitions object=deal
```

You should see all three. If not, the customer probably created them on the wrong object — verify they're on Deal, not Company or Person.

## Workspace verification

Per the user's `user_attio_workspace.md` memory: **always verify the workspace via `whoami` before any write**. The Craftt workspace is the only one to use. If the MCP is connected to a different workspace, stop and reconnect.

```
whoami
```

If the workspace isn't "Craftt" (or the customer's own workspace you've been added to as an expert), do not proceed.

## Identifying the deals list

The agent scans an Attio list, not the raw Deal object. Lists let the customer scope what's "open" — usually a list filtered to non-closed stages.

To find the right list:

```
list-lists
```

Look for names like "Open Deals", "Active Pipeline", "Q3 Pipeline". If multiple match, ask the customer which one the agent should scan. Store the list ID in the customer config.

If no suitable list exists, walk the customer through creating one in the Attio UI. Filter: stage is not Closed-Won or Closed-Lost. Sort: amount desc.

## Stage mapping

The agent's stage weights (in [scoring.md](scoring.md)) assume canonical stage names. Real customers have their own names. Map them during setup.

```
list-attribute-definitions object=deal
```

Find the `stage` attribute. List its options. Map each to a canonical weight:

```yaml
# example customer config
stage_weights:
  "New Lead": 0.5         # Discovery equivalent
  "Qualified": 0.5
  "Demo Scheduled": 0.8
  "Proposal Sent": 1.0
  "Negotiation": 1.2
  "Contract Out": 1.5
  "Won": 0                # excluded
  "Lost": 0               # excluded
```

If the customer has more stages than the canonical set, group them. If they have fewer, just leave the unused canonical stages out of the config.

## Configuration

Per-customer config file. Default location: `customers/{customer_slug}/deal-focus-config.yaml` in whatever repo holds the customer's implementation.

```yaml
customer:
  name: "Acme Inc"
  attio_workspace: "Craftt"   # always verified, never trust the config
  founder_user:
    slack_id: "U01234567"
    email: "founder@acme.com"
  timezone: "America/New_York"

pipeline:
  list_id: "list_abc123"
  threshold_amount: 10000     # ignore deals under this
  lookback_days: 30

stages:
  weights:
    "New Lead": 0.5
    "Qualified": 0.5
    "Demo Scheduled": 0.8
    "Proposal Sent": 1.0
    "Negotiation": 1.2
    "Contract Out": 1.5

signals:
  # override default weights from signals.md per customer
  weights:
    decision_maker_pulling_away: 25   # bumped from default 22
    pricing_pushback_unresolved: 14   # lowered from 18

scoring:
  bucket_thresholds:
    yellow_at: 30
    red_at: 60
  diversity_rule: true
  freshness_rule: true
  top_n: 5

delivery:
  channels: ["slack"]         # slack | email | notion | attio_only
  schedule:
    cron: "0 20 * * 0"        # Sun 8pm in customer's tz
    twice_weekly: false
```

The config lives next to the customer-specific code so it can be committed and versioned. Don't store it in the customer's Attio.

## What the Attio MCP cannot do — and the workarounds

Per the user's `reference_attio_mcp_limits.md` memory and verified by `list-attribute-definitions` behavior:

| Operation | MCP support | Workaround |
|-----------|-------------|------------|
| Create attribute | ❌ | Customer creates in Attio UI; MCP verifies via list-attribute-definitions |
| Create object | ❌ | Same — UI only |
| Delete record | ❌ | Don't delete from agent. Mark as archived via a flag attribute if needed. |
| Update record | ✅ | Standard. |
| Create note | ✅ | Standard. |
| Read list-records | ✅ | Standard. |
| Search calls/emails/notes | ✅ | Use semantic-search variants for content lookup; metadata search for date filters. |

If the customer says "the agent should also create new Deal records", that's out of scope. Tell them: the agent surfaces signal on existing deals; deal creation is the rep's job (or a different agent).

## Expert access reminder

Per the user's `project_attio_expert_access.md` memory: when implementing for a customer, the customer adds George (you) to their Attio as an expert. **No extra seat, full access, never "read-only".** If the customer is offering you read-only access, push back — the agent has to write to update health, write notes, etc.

## Dry-run before turning on the cron

After setup, before turning on the Sunday cron, run the agent in demo mode against 3–5 deals the founder knows well. Walk through the output together:

- Does the health score match the founder's gut?
- Is the reasoning citing the right calls and emails?
- Are the suggested actions specific enough?

Tune signal weights based on what they push back on. This is the moment to learn the customer's pipeline — not in production on a Monday morning.

After they sign off, install the cron. Send the first real digest manually-supervised the following Monday so you can fix anything embarrassing before they see it.
