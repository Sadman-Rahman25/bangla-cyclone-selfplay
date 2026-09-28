"""Validate cyclone-line outlines and compare diversity with a scripted baseline."""
import collections
import json
import random

from selfplay import SHELTERS, api_find_shelter, scripted_baseline

RESOLUTIONS = ("inform", "notify_success", "escalate_rescue", "escalate_officer")


def signature(turn):
    return tuple((a, s if a in ("inform", "request") else None) for a, s, _ in turn["acts"])


def diversity(dialogues, k=3):
    total = sum(len(d["turns"]) for d in dialogues)
    trans, subs, n_subs, outlines = set(), set(), 0, set()
    for d in dialogues:
        sig = [signature(t) for t in d["turns"]]
        trans.update(zip(sig, sig[1:]))
        for i in range(len(sig) - k):
            subs.add(tuple(sig[i:i + k + 1])); n_subs += 1
        outlines.add(tuple(sig))
    return {"unique_transitions_per_turn": len(trans) / total,
            "unique_subdialogues_k3": len(subs) / max(n_subs, 1),
            "unique_outlines_ratio": len(outlines) / len(dialogues)}


def check_invariants(d):
    g, errors, informed = d["goal"], [], set()
    acts = [(t["speaker"], a, s, v) for t in d["turns"] for a, s, v in t["acts"]]
    for sp, a, s, v in acts:
        if sp == "U" and a == "inform":
            informed.add(s)
        if sp == "S" and a == "request" and s in informed:
            errors.append(f"I1 re-requested {s}")
        if sp == "S" and a == "offer":
            caps = dict(SHELTERS.get(g.get("location"), []))
            if v not in caps or caps[v] < g["household_size"]:
                errors.append("I2 invalid shelter offer")
    sys_acts = [a for sp, a, _, _ in acts if sp == "S"]
    needs_rescue = g["status"] == "rescue" or ("offer" in sys_acts and not g.get("can_travel", True))
    if needs_rescue and ("escalate_rescue" not in sys_acts or "notify_success" in sys_acts):
        errors.append("I3 rescue need not escalated")
    for sp, a, s, v in acts:
        if a == "escalate_rescue":
            want = "high" if g.get("vulnerable") not in (None, "নেই") else "normal"
            if v != want:
                errors.append("I4 wrong priority")
    if g["status"] == "shelter" and g.get("location") != "অজানা":
        if ("escalate_officer" in sys_acts) != (api_find_shelter(g["location"], g["household_size"]) is None):
            errors.append("I5 capacity handling wrong")
    if acts[-1][1] != "bye" or not any(a in RESOLUTIONS for a in sys_acts):
        errors.append("I6 caller left unresolved")
    return errors


def outcome(d):
    sys_acts = [a for t in d["turns"] if t["speaker"] == "S" for a, _, _ in t["acts"]]
    if "escalate_rescue" in sys_acts:
        return "rescue_after_shelter_refusal" if "offer" in sys_acts else "rescue_escalated"
    if "escalate_officer" in sys_acts:
        reason = [v for t in d["turns"] for a, _, v in t["acts"] if a == "escalate_officer"][0]
        return "location_unknown" if reason == "location_unknown" else "no_shelter_capacity"
    if "notify_success" in sys_acts:
        return "shelter_confirmed"
    return "safe_advice"


if __name__ == "__main__":
    outlines = [json.loads(l) for l in open("outlines.jsonl", encoding="utf-8")]
    violations = [(i, e) for i, d in enumerate(outlines) for e in check_invariants(d)]
    print(f"Invariant violations: {len(violations)} across {len(outlines)} outlines")
    for v in violations[:8]:
        print("  ", v)
    print("\nOutcome distribution:")
    for k, v in collections.Counter(outcome(d) for d in outlines).most_common():
        print(f"  {k:<30}{v:>5}  ({v / len(outlines):.1%})")
    lengths = [len(d["turns"]) for d in outlines]
    print(f"\nTurns per dialogue: mean {sum(lengths)/len(lengths):.2f}, min {min(lengths)}, max {max(lengths)}")
    rng = random.Random(2026)
    base = [scripted_baseline(rng) for _ in range(len(outlines))]
    sp, bl = diversity(outlines), diversity(base)
    print("\nDiversity (self-play vs scripted):")
    for k in sp:
        print(f"  {k:<30} {sp[k]:.4f}   {bl[k]:.4f}")
