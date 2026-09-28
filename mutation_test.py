"""Inject one known fault per invariant; the checker must flag every mutant."""
import copy, json
from evaluate_outlines import check_invariants, outcome

outs = [json.loads(l) for l in open("outlines.jsonl", encoding="utf-8")]
pick = {}
for d in outs:
    pick.setdefault(outcome(d), d)

def acts_of(d):
    return [a for t in d["turns"] for a in t["acts"]]

def mutant(kind):
    if kind == "I1 re-request":
        d = copy.deepcopy(pick["rescue_escalated"])
        d["turns"].insert(-2, {"speaker": "S", "acts": [["request", "location", None]]})
    elif kind == "I2 invalid shelter":
        d = copy.deepcopy(pick["shelter_confirmed"])
        for a in acts_of(d):
            if a[0] == "offer": a[2] = "অস্তিত্বহীন আশ্রয়কেন্দ্র"
    elif kind == "I3 rescue dropped":
        d = copy.deepcopy(pick["rescue_escalated"])
        for t in d["turns"]:
            t["acts"] = [a for a in t["acts"] if a[0] != "escalate_rescue"] or [["inform", "advice", "stay_alert"]]
    elif kind == "I4 wrong priority":
        d = copy.deepcopy(next(o for o in outs if outcome(o) == "rescue_escalated" and o["goal"]["vulnerable"] != "নেই"))
        for a in acts_of(d):
            if a[0] == "escalate_rescue": a[2] = "normal"
    elif kind == "I5 capacity ignored":
        d = copy.deepcopy(pick["no_shelter_capacity"])
        for t in d["turns"]:
            t["acts"] = [["offer", "shelter", "কুতুবদিয়া আশ্রয়কেন্দ্র"] if a[0] == "escalate_officer" else a for a in t["acts"]]
    elif kind == "I6 unresolved":
        d = copy.deepcopy(pick["safe_advice"])
        for t in d["turns"]:
            t["acts"] = [a for a in t["acts"] if a[0] != "inform" or t["speaker"] == "U"] or [["greeting", None, None]]
    return d

kinds = ["I1 re-request", "I2 invalid shelter", "I3 rescue dropped", "I4 wrong priority", "I5 capacity ignored", "I6 unresolved"]
caught = 0
for k in kinds:
    errs = check_invariants(mutant(k)); caught += bool(errs)
    print(f"{k:<22} detected={bool(errs)}  {errs}")
print(f"\nMutants detected: {caught}/{len(kinds)}")
