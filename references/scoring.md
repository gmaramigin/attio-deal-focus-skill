# Scoring and Ranking

Two separate decisions:

1. **Per-deal risk score** — how risky is this deal right now? Computed from the fired signals. Deterministic.
2. **Top-5 priority** — which deals should the founder focus on this week? Combines risk score, deal amount, and stage weight.

Keep the two separate. Risk is about the deal's state. Priority is about where the founder's hour spent today returns the most.

## Risk score

```
raw_risk = sum(weight of each fired risk signal)
positive_offset = max(-25, sum(weight of each fired positive signal))
risk_score = clamp(0, 100, raw_risk + positive_offset)
```

The risk signal weights live in [signals.md](signals.md). The orchestrator owns the computation, not the model. That's deliberate — when a customer says "I care more about silence than pricing pushback", you adjust the weight in the config without retraining the prompt.

Default weight sum on the high end is ~100 (every red flag firing). Most deals score 20–70.

### Confidence gate

If the model returns `confidence < 0.4`, the deal is `unknown` regardless of risk score. Empty bundles produce phantom risk. Better to surface "we don't have signal on this one yet" than to score a deal red because the bundle was thin.

### Health bucketing

| Risk score | Health |
|------------|--------|
| 0–29 | Green |
| 30–59 | Yellow |
| 60–100 | Red |
| (any score, confidence < 0.4) | Unknown |

Bucket thresholds are tunable per customer. Some founders want stricter gates ("yellow at 25, red at 50") to surface more deals; others want looser to keep the digest sparse.

## Priority score for top-5

```
priority = risk_score × deal_amount × stage_weight
```

### Stage weights

Why stage matters: a $50k deal in Discovery is usually less actionable than a $50k deal in Negotiation. Action this week pays off bigger when the deal is closer to a decision.

| Stage | Weight |
|-------|--------|
| Discovery / Qualification | 0.5 |
| Demo / Evaluation | 0.8 |
| Proposal | 1.0 |
| Negotiation | 1.2 |
| Contract sent | 1.5 |
| Closed-won / Closed-lost | 0 (excluded) |

Customers with different stage names — `list-attribute-definitions` will surface what's in their workspace. Map manually during setup.

### Worked example

Deal A: $20k, Red (risk 75), in Discovery
→ priority = 75 × 20000 × 0.5 = 750,000

Deal B: $15k, Yellow (risk 45), in Negotiation
→ priority = 45 × 15000 × 1.2 = 810,000

Deal B wins. Lower risk score, but it's closer to a decision and your action this week matters more.

This is the formula's whole point. It's the gap between "what's the riskiest deal" and "what should I do something about today."

## Top-5 selection

After computing priority for every open deal:

1. Sort by priority desc.
2. Take the top 5.
3. Apply the **diversity rule**: if 4 of the top 5 have the same owner, swap the lowest-priority one for the next non-same-owner deal. The founder wants pipeline coverage, not 5 fires from one rep.
4. Apply the **freshness rule**: if a deal was in last Monday's top 5 and the founder took no action on it (no new outbound from owner, no new note), keep it in unless 3+ new deals score higher. Avoid digest churn.

### When fewer than 5 deals are scored

Some customers won't have 5 deals worth flagging on a given Monday. Default behavior: deliver however many qualify, even if it's 2. Don't pad with green deals to hit a number.

If a customer wants a fixed-5 digest regardless ("I want my Monday ritual"), drop the priority threshold and include greens — but tag them as "tracking, not at risk" in the digest.

## Persistent state across runs

The agent should remember last Monday's top 5 to:

- Detect deals that got worse week-over-week ("this was Yellow last Monday, Red today, founder didn't act")
- Skip already-actioned deals ("founder DID act, risk reduced from Red to Yellow — celebrate it briefly in the digest preamble")

Store this in a simple JSON file or Attio note attached to a meta record. Don't overbuild — this is one row per week per customer.

## Tunable knobs summary

When a customer asks "can you change X" during the retainer, here's what's tunable without prompt changes:

- Signal weights (per signal, per customer)
- Bucket thresholds (Yellow at X, Red at Y)
- Stage weights
- Threshold for "open deal" amount (default $10k)
- Lookback window (default 30 days)
- Diversity / freshness rule on/off
- Top-N (default 5)

What's NOT tunable without prompt or code work:

- Adding a new signal type (requires prompt edit + weight)
- Changing the digest format (requires template edit)
- Changing the model (Sonnet default; would change quality/cost)
