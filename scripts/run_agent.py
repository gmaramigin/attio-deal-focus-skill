"""
Deal Focus Agent — reference runner.

Fork this per customer. The Anthropic SDK piece is production-shaped; the
Attio adapter functions are stubs you wire to the customer's MCP setup
(attio-mcp Python wrapper, REST, or claude-desktop MCP bridge).

Usage:
    python run_agent.py batch  --config customers/acme/config.yaml
    python run_agent.py demo   --config customers/acme/config.yaml --deal-id rec_abc123

Reads config from a YAML file. See references/attio-setup.md for the schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2000

# ---------------------------------------------------------------------------
# Signal weights (see references/signals.md for definitions)
# Customer config can override these.
# ---------------------------------------------------------------------------

DEFAULT_RISK_WEIGHTS = {
    "pricing_pushback_unresolved": 18,
    "decision_maker_pulling_away": 22,
    "competitor_positive_mention": 15,
    "timeline_slipping_no_date": 14,
    "internal_blocker_named": 12,
    "vague_next_step": 10,
    "champion_losing_energy": 12,
    "no_outbound_owner": 15,
    "generic_check_in_last_touch": 8,
    "stage_thrashing": 10,
    "owner_changed_recently": 8,
    "no_champion_identified": 10,
    "response_time_degrading": 14,
    "manager_cc_silence": 12,
    "repeated_hedging": 10,
}

DEFAULT_POSITIVE_WEIGHTS = {
    "specific_implementation_question": -8,
    "multiple_stakeholders_engaged": -10,
    "we_when_we_deploy_language": -6,
    "asking_about_terms": -10,
}

DEFAULT_STAGE_WEIGHTS = {
    "discovery": 0.5,
    "qualification": 0.5,
    "demo": 0.8,
    "proposal": 1.0,
    "negotiation": 1.2,
    "contract_sent": 1.5,
}


# ---------------------------------------------------------------------------
# System prompt — cached prefix, byte-identical across deals in a batch.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the Deal Focus Agent. You analyze one deal at a time and return a
structured assessment that helps the founder decide which deals to focus on
this week.

For each deal you read:
- Recent call transcripts (3-5)
- Recent emails (5-10)
- Notes the team has written
- Open tasks
- CRM activity facts (last outbound, stage history, owner changes, champion)

You return ONE JSON object matching the output schema. You never make up
quotes or signals. Every signal you fire must cite a specific call date,
email date, or note. If the bundle is empty or you can't find evidence,
return confidence: 0 and stop.

# Risk signals (conversations)
- pricing_pushback_unresolved: pricing concern raised >1x and never addressed
- decision_maker_pulling_away: DM attended early calls, skipped recent ones
- competitor_positive_mention: buyer mentions competitor in positive framing
- timeline_slipping_no_date: "circle back next quarter" no committed date
- internal_blocker_named: procurement/legal/manager blocker unresolved
- vague_next_step: last call ended without committed next step
- champion_losing_energy: champion participating less over time

# Risk signals (CRM, given as facts)
- no_outbound_owner
- generic_check_in_last_touch
- stage_thrashing
- owner_changed_recently
- no_champion_identified

# Risk signals (emails)
- response_time_degrading: buyer's reply latency grew >2x vs early deal
- manager_cc_silence: senior person CC'd then never replied
- repeated_hedging: hedging language used 2+ times

# Positive signals (reduce risk)
- specific_implementation_question: SSO, migration, API, rollout questions
- multiple_stakeholders_engaged: multiple buyer-side people actively contributing
- we_when_we_deploy_language: mental ownership
- asking_about_terms: pricing tiers, contract length, references, MSA

# How you reason
1. Read the bundle.
2. List every signal that fires, with evidence (date + quote or paraphrase).
3. List every positive signal that fires, same format.
4. Draft 2-3 sentence reasoning the founder will read in a Slack DM. Cite
   specific dates. Be concrete. No corporate language. No em dashes.
5. Propose a specific next action this week. Not "follow up". One step.
6. Estimate the dollar stake. Usually deal amount; surface expansion if obvious.
7. Set confidence based on bundle richness. <0.4 means insufficient data.

# Output schema
{
  "deal_id": str,
  "health": "red" | "yellow" | "green" | "unknown",
  "risk_score": int,
  "top_signals": [{"signal": str, "evidence": str}],
  "positive_signals": [{"signal": str, "evidence": str}],
  "reasoning": str,
  "suggested_action": str,
  "stake_estimate": {"amount": int, "currency": "USD", "expansion_note": str},
  "confidence": float
}

Return only the JSON object. No prose around it.
"""


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Deal:
    id: str
    name: str
    amount: int
    stage: str
    owner: str
    days_in_stage: int
    days_since_created: int


@dataclass
class CrmFacts:
    last_outbound_date: str | None
    last_outbound_days_ago: int | None
    last_outbound_is_generic: bool
    stage_transitions_30d: list[dict[str, str]]
    owner_changed_30d: bool
    previous_owner: str | None
    has_champion: bool
    champion_name: str | None


@dataclass
class DealBundle:
    deal: Deal
    crm: CrmFacts
    calls: list[dict[str, Any]]    # {"date": ..., "transcript": ..., "attendees": [...]}
    emails: list[dict[str, Any]]   # {"date": ..., "from": ..., "to": ..., "body": ...}
    notes: list[dict[str, Any]]    # {"date": ..., "author": ..., "body": ...}
    tasks: list[dict[str, Any]]    # {"due": ..., "title": ..., "status": ...}


@dataclass
class DealAnalysis:
    deal_id: str
    health: str
    risk_score: int                # recomputed by orchestrator, not trusted from model
    model_risk_score: int          # what the model returned, for telemetry
    top_signals: list[dict[str, str]]
    positive_signals: list[dict[str, str]]
    reasoning: str
    suggested_action: str
    stake_amount: int
    expansion_note: str
    confidence: float
    priority: float = 0.0


# ---------------------------------------------------------------------------
# Attio adapter — STUBS. Wire to your MCP / REST layer.
# ---------------------------------------------------------------------------

def attio_whoami() -> str:
    """Verify Craftt workspace before any write. Raise if wrong workspace."""
    raise NotImplementedError("wire to attio MCP whoami")


def attio_list_open_deals(list_id: str, threshold: int) -> list[Deal]:
    raise NotImplementedError("wire to attio list-records on the deals list")


def attio_pull_bundle(deal_id: str, lookback_days: int) -> DealBundle:
    """
    Fetch calls (semantic-search-call-recordings + get-call-recording),
    emails (search-emails-by-metadata + get-email-content),
    notes (semantic-search-notes + get-note-body),
    tasks (list-tasks), meetings (search-meetings).
    Compute CrmFacts locally.
    """
    raise NotImplementedError("wire to attio MCP bundle fetch")


def attio_write_health(deal_id: str, health: str, risk_score: int) -> None:
    raise NotImplementedError("wire to attio update-record")


def attio_write_reasoning_note(deal_id: str, reasoning: str, action: str, health: str) -> None:
    raise NotImplementedError("wire to attio create-note")


# ---------------------------------------------------------------------------
# Claude per-deal call
# ---------------------------------------------------------------------------

def build_user_message(bundle: DealBundle) -> str:
    d, c = bundle.deal, bundle.crm
    calls = "\n\n".join(
        f"### Call {i+1} — {call['date']} — attendees: {', '.join(call.get('attendees', []))}\n{call['transcript']}"
        for i, call in enumerate(bundle.calls)
    ) or "(none)"
    emails = "\n\n".join(
        f"### Email {i+1} — {e['date']} — from {e['from']} to {', '.join(e.get('to', []))}\n{e['body']}"
        for i, e in enumerate(bundle.emails)
    ) or "(none)"
    notes = "\n\n".join(
        f"### Note {i+1} — {n['date']} — {n['author']}\n{n['body']}"
        for i, n in enumerate(bundle.notes)
    ) or "(none)"
    tasks = "\n".join(f"- {t['title']} (due {t.get('due', '?')}, {t.get('status', '?')})" for t in bundle.tasks) or "(none)"

    return f"""\
Deal: {d.name}
Amount: ${d.amount:,}
Stage: {d.stage}
Owner: {d.owner}
Days in current stage: {d.days_in_stage}
Days since deal created: {d.days_since_created}

# CRM activity facts
Last outbound from owner: {c.last_outbound_date} ({c.last_outbound_days_ago} days ago)
Last outbound was generic check-in: {c.last_outbound_is_generic}
Stage transitions in last 30 days: {len(c.stage_transitions_30d)} ({c.stage_transitions_30d})
Owner changed in last 30 days: {c.owner_changed_30d} (previous: {c.previous_owner})
Champion identified: {c.has_champion} ({c.champion_name or 'none'})

# Calls
{calls}

# Emails
{emails}

# Notes
{notes}

# Open tasks
{tasks}

Return one JSON object matching the schema. No prose outside the JSON.
"""


def score_deal(client: Anthropic, bundle: DealBundle) -> dict[str, Any]:
    """One Claude call per deal. Returns parsed JSON dict."""
    user_text = build_user_message(bundle)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
    )

    print(
        f"[telemetry] deal={bundle.deal.id} "
        f"cache_write={response.usage.cache_creation_input_tokens} "
        f"cache_read={response.usage.cache_read_input_tokens} "
        f"output={response.usage.output_tokens}",
        file=sys.stderr,
    )

    raw = response.content[0].text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # one retry with a JSON-only reminder
        retry = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[
                {"role": "user", "content": [{"type": "text", "text": user_text}]},
                {"role": "assistant", "content": [{"type": "text", "text": raw}]},
                {"role": "user", "content": [{"type": "text", "text": "That was not valid JSON. Return only the JSON object, no prose."}]},
            ],
        )
        return json.loads(retry.content[0].text)


# ---------------------------------------------------------------------------
# Scoring math — deterministic, owned by orchestrator
# ---------------------------------------------------------------------------

def recompute_risk(parsed: dict, weights: dict[str, int]) -> int:
    fired = [s["signal"] for s in parsed.get("top_signals", [])]
    fired_positive = [s["signal"] for s in parsed.get("positive_signals", [])]
    raw = sum(weights.get(s, 0) for s in fired)
    offset = max(-25, sum(weights.get(s, 0) for s in fired_positive))
    return max(0, min(100, raw + offset))


def bucket_health(risk: int, confidence: float, yellow_at: int, red_at: int) -> str:
    if confidence < 0.4:
        return "unknown"
    if risk >= red_at:
        return "red"
    if risk >= yellow_at:
        return "yellow"
    return "green"


def priority(deal: Deal, risk: int, stage_weights: dict[str, float]) -> float:
    stage_key = deal.stage.lower().replace(" ", "_")
    weight = stage_weights.get(stage_key, 0.5)
    return risk * deal.amount * weight


def make_analysis(parsed: dict, deal: Deal, config: dict) -> DealAnalysis:
    weights = {**DEFAULT_RISK_WEIGHTS, **DEFAULT_POSITIVE_WEIGHTS, **config.get("signals", {}).get("weights", {})}
    risk = recompute_risk(parsed, weights)
    confidence = parsed.get("confidence", 0.0)
    health = bucket_health(
        risk,
        confidence,
        config.get("scoring", {}).get("bucket_thresholds", {}).get("yellow_at", 30),
        config.get("scoring", {}).get("bucket_thresholds", {}).get("red_at", 60),
    )
    stake = parsed.get("stake_estimate", {})
    return DealAnalysis(
        deal_id=deal.id,
        health=health,
        risk_score=risk,
        model_risk_score=parsed.get("risk_score", risk),
        top_signals=parsed.get("top_signals", []),
        positive_signals=parsed.get("positive_signals", []),
        reasoning=parsed.get("reasoning", ""),
        suggested_action=parsed.get("suggested_action", ""),
        stake_amount=stake.get("amount", deal.amount),
        expansion_note=stake.get("expansion_note", ""),
        confidence=confidence,
    )


def select_top_n(analyses: list[DealAnalysis], deals: dict[str, Deal], config: dict) -> list[DealAnalysis]:
    stage_weights = {**DEFAULT_STAGE_WEIGHTS, **config.get("stages", {}).get("weights", {})}
    for a in analyses:
        a.priority = priority(deals[a.deal_id], a.risk_score, stage_weights)
    analyses.sort(key=lambda a: a.priority, reverse=True)
    top = analyses[: config.get("scoring", {}).get("top_n", 5)]
    # diversity / freshness rules can be applied here; left as exercise
    return top


# ---------------------------------------------------------------------------
# Digest formatting (see references/digest.md)
# ---------------------------------------------------------------------------

HEALTH_EMOJI = {"red": "🔴", "yellow": "🟡", "green": "🟢", "unknown": "⚪"}


def format_entry(a: DealAnalysis, deal: Deal) -> str:
    stake_line = f"Stake: ${a.stake_amount:,} now"
    if a.expansion_note:
        stake_line += f". {a.expansion_note}"
    stage_status = f"{deal.stage}, {deal.days_in_stage} days"
    return (
        f"{HEALTH_EMOJI[a.health]} {deal.name} — ${deal.amount:,} — {stage_status}\n\n"
        f"Why: {a.reasoning}\n\n"
        f"Do this week: {a.suggested_action}\n\n"
        f"{stake_line}"
    )


def format_digest(top: list[DealAnalysis], deals: dict[str, Deal], date: str) -> str:
    n_red = sum(1 for a in top if a.health == "red")
    n_yellow = sum(1 for a in top if a.health == "yellow")
    total_stake = sum(a.stake_amount for a in top)
    summary = f"{n_red} reds, {n_yellow} yellows. ${total_stake:,} at stake."
    entries = "\n\n".join(format_entry(a, deals[a.deal_id]) for a in top)
    return (
        f"Monday focus, {date}.\n\n"
        f"{len(top)} deals to focus on this week. {summary}\n\n"
        f"{entries}\n\n"
        "Full deal health updated in Attio. Reply if any of these scored wrong — helps tune next week."
    )


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_batch(config: dict, client: Anthropic) -> None:
    attio_whoami()
    deals = attio_list_open_deals(
        config["pipeline"]["list_id"],
        config["pipeline"]["threshold_amount"],
    )
    deal_by_id = {d.id: d for d in deals}

    analyses: list[DealAnalysis] = []
    for deal in deals:
        bundle = attio_pull_bundle(deal.id, config["pipeline"]["lookback_days"])
        parsed = score_deal(client, bundle)
        analysis = make_analysis(parsed, deal, config)
        attio_write_health(deal.id, analysis.health, analysis.risk_score)
        attio_write_reasoning_note(deal.id, analysis.reasoning, analysis.suggested_action, analysis.health)
        analyses.append(analysis)

    top = select_top_n(analyses, deal_by_id, config)
    digest = format_digest(top, deal_by_id, datetime.now(timezone.utc).strftime("%B %d"))

    # delivery: replace with Slack / email / Notion adapter per config
    print(digest)


def run_demo(config: dict, client: Anthropic, deal_id: str) -> None:
    bundle = attio_pull_bundle(deal_id, config["pipeline"]["lookback_days"])
    # demo trims bundle for speed
    bundle.calls = bundle.calls[:3]
    bundle.emails = bundle.emails[:5]
    parsed = score_deal(client, bundle)
    analysis = make_analysis(parsed, bundle.deal, config)
    print(format_entry(analysis, bundle.deal))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["batch", "demo"])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--deal-id", help="required for demo mode")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text())
    client = Anthropic()

    if args.mode == "batch":
        run_batch(config, client)
    elif args.mode == "demo":
        if not args.deal_id:
            sys.exit("demo mode requires --deal-id")
        run_demo(config, client, args.deal_id)


if __name__ == "__main__":
    main()
