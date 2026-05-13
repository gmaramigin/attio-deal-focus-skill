# Signal Taxonomy

The agent reads three streams and looks for specific patterns. This file is the canonical list. The Claude per-deal prompt embeds an abridged version of it; this file is the source of truth for tuning and debugging.

Each signal has a **name**, a **what to look for** description, an **evidence pattern** (what the model should cite when it fires the signal), and a **default weight** for the risk score. Weights are tunable per customer.

The model returns signals as `{ "signal": "<name>", "evidence": "<quote or paraphrase + source>" }`. Never let the model invent the evidence — that's the cardinal rule.

## Risk signals — conversations (calls + meetings)

### pricing_pushback_unresolved
**What:** Pricing concern raised more than once across calls and never resolved with a concrete answer.
**Evidence:** Quote the buyer's pricing concern from call N, then show that follow-up calls and emails don't address it.
**Weight:** 18

### decision_maker_pulling_away
**What:** The named decision-maker attended early calls but skipped recent ones. Champion-only meetings replacing exec-attended meetings.
**Evidence:** "On call 1 (date), DM was present. On calls 3 and 4 (dates), DM declined or no-showed."
**Weight:** 22

### competitor_positive_mention
**What:** Buyer talks about a competitor with positive framing or as the comparison point. "We're also looking at X." "X already does this."
**Evidence:** Quote the competitor mention with date and speaker.
**Weight:** 15

### timeline_slipping_no_date
**What:** "Let's circle back next quarter / when we have budget / after Q3" with no committed date.
**Evidence:** Quote the vague timeline plus the absence of a committed next step.
**Weight:** 14

### internal_blocker_named
**What:** Buyer surfaces an internal blocker — procurement, legal, security, manager approval — that hasn't been addressed.
**Evidence:** "On call 3, buyer said 'I need to check with procurement.' No procurement contact or document exchange follows in the emails."
**Weight:** 12

### vague_next_step
**What:** Last call ended without a committed next step. "We'll let you know" or "we'll get back to you" without a date.
**Evidence:** Quote the closing exchange from the most recent call.
**Weight:** 10

### champion_losing_energy
**What:** Champion's call participation degrades over time. Less talking, fewer questions, calls getting shorter.
**Evidence:** Compare call lengths or participation rates across the lookback window. Cite specific call dates.
**Weight:** 12

## Risk signals — CRM activity

These are computed deterministically by the orchestrator before the Claude call. The prompt receives them as facts, not as something to infer.

### no_outbound_owner
**What:** No outbound message from the deal owner in N days. N varies by stage:
- Discovery / Qualification: 7 days
- Proposal / Negotiation: 5 days
- Contract sent: 3 days
**Evidence:** Last outbound date and stage.
**Weight:** 15

### generic_check_in_last_touch
**What:** Last outbound was a generic "just checking in" / "wanted to follow up" message with no substance.
**Evidence:** Quote the message. Generic = no specific reference to prior conversation, no document attached, no proposed time.
**Weight:** 8

### stage_thrashing
**What:** Deal moved across stages more than twice in the last 30 days.
**Evidence:** List the stage transitions with dates.
**Weight:** 10

### owner_changed_recently
**What:** Deal owner changed in the last 30 days. Handover risk — context may have been lost.
**Evidence:** Previous owner, new owner, transition date.
**Weight:** 8

### no_champion_identified
**What:** No person on the deal is tagged as champion, primary contact, or equivalent.
**Evidence:** "Deal has N contacts attached, none marked as champion."
**Weight:** 10

## Risk signals — emails

### response_time_degrading
**What:** Buyer's median response time has grown by more than 2x compared to the early-deal baseline.
**Evidence:** "Early in the deal (date range), buyer replied in ~2 hours. Last 3 replies: 3 days, 2 days, 4 days."
**Weight:** 14

### manager_cc_silence
**What:** A manager or senior stakeholder was CC'd into the thread and never replied.
**Evidence:** "Manager Pradeep CC'd on email (date). No reply in subsequent N emails."
**Weight:** 12

### repeated_hedging
**What:** Buyer used hedging language ("we need to think about it", "let me get back to you", "not sure yet") twice or more across recent emails.
**Evidence:** Quote each hedging instance with date.
**Weight:** 10

## Positive signals

These reduce the risk score and are worth surfacing in the digest reasoning because the founder wants to see momentum, not just smoke. Each positive signal subtracts from the raw risk score (cap the reduction at -25 total so positive signals can't whitewash a bad deal).

### specific_implementation_question
**What:** Buyer asks an implementation question that only makes sense if they're seriously considering buying. SSO setup, data migration timing, API rate limits, rollout plan.
**Evidence:** Quote the question with date and source.
**Weight:** -8

### multiple_stakeholders_engaged
**What:** Multiple buyer-side people are actively participating across calls and emails. Not just CC'd — actually contributing.
**Evidence:** Name the stakeholders, cite a contribution from each.
**Weight:** -10

### we_when_we_deploy_language
**What:** Buyer uses "we" or "when we deploy" / "once we're live" language. Mental ownership.
**Evidence:** Quote the line with date.
**Weight:** -6

### asking_about_terms
**What:** Buyer asks specifically about pricing tiers, contract length, references, payment terms, MSA. Procurement-grade questions.
**Evidence:** Quote the question.
**Weight:** -10

## Scoring assembly

The Claude prompt returns the list of fired signals with evidence. The orchestrator computes:

```
raw_risk = sum(weight of each fired risk signal)
positive_offset = max(-25, sum(weight of each fired positive signal))
risk_score = clamp(0, 100, raw_risk + positive_offset)
```

The model may also return `confidence` on a 0–1 scale based on how much bundle data it had. If `confidence < 0.4`, mark the deal `unknown` rather than emit a misleading health color.

Health bucketing (default, tunable per customer):
- Red: risk_score >= 60
- Yellow: 30 <= risk_score < 60
- Green: risk_score < 30
- Unknown: confidence < 0.4 OR bundle was empty

## Tuning weights per customer

Some customers care more about specific signals. A founder selling to enterprise will weight `internal_blocker_named` and `manager_cc_silence` higher. A founder selling to SMBs will weight `response_time_degrading` and `vague_next_step` higher.

Store per-customer overrides in the customer config file. When the customer asks "why is this red?" and the answer surfaces a signal they don't care about, that's a signal to retune. Bring them the weight table on the next call.

## Signals NOT to include

Resist the urge to add these. They sound smart and produce noise:

- **Sentiment analysis on call transcripts.** Too noisy; the specific signals above already capture sentiment that matters.
- **Word counts or "talk ratio" between rep and buyer.** Sales-coaching territory, not deal-risk territory.
- **Anything that grades the rep.** Politically explosive. The agent's output ranks deals, not people.
- **External signals** (news mentions, layoffs, funding rounds). Out of scope for v1. Adds noise and cost.
