"""Miniature M2M self-play for a Bangla cyclone and flood response line.

Components follow Shah et al. (2018): a task schema and API supplied by the
developer, a scenario sampler (goal + profile), an agenda-based user
simulator and a finite-state system agent. Dialogues are emitted as
dialogue-act outlines with Bangla templates.
"""
import json
import random

UPAZILAS = ["কয়রা", "শ্যামনগর", "কলাপাড়া", "হাতিয়া", "কুতুবদিয়া"]
VULNERABLE = ["বয়স্ক", "শিশু", "অন্তঃসত্ত্বা", "প্রতিবন্ধী", "নেই"]
LANDMARKS = ["বড় মসজিদের পাশে", "প্রাইমারি স্কুলের কাছে", "বাজারের পাশে"]

# Mock shelter database: upazila -> [(shelter, remaining capacity)].
# Kutubdia is deliberately full, creating unsatisfiable shelter requests.
SHELTERS = {
    "কয়রা": [("কয়রা সদর আশ্রয়কেন্দ্র", 40), ("মহারাজপুর আশ্রয়কেন্দ্র", 6)],
    "শ্যামনগর": [("গাবুরা আশ্রয়কেন্দ্র", 12)],
    "কলাপাড়া": [("কলাপাড়া হাই স্কুল আশ্রয়কেন্দ্র", 25), ("ধানখালী আশ্রয়কেন্দ্র", 3)],
    "হাতিয়া": [("হাতিয়া সদর আশ্রয়কেন্দ্র", 8)],
    "কুতুবদিয়া": [("কুতুবদিয়া আশ্রয়কেন্দ্র", 0)],
}


def api_find_shelter(upazila, size):
    """First shelter in the upazila with enough remaining capacity, else None."""
    for name, cap in SHELTERS.get(upazila, []):
        if cap >= size:
            return name
    return None


def required_slots(state):
    status = state.get("status")
    if status is None:
        return ["status"]
    if status == "safe":
        return []
    slots = ["location"]
    if state.get("location") == "অজানা":
        slots.append("landmark")
    slots.append("household_size")
    if status == "rescue":
        slots.append("vulnerable")
    return slots


# ----------------------------------------------------------- scenario --
def sample_scenario(rng):
    status = rng.choices(["safe", "shelter", "rescue"], weights=[0.3, 0.4, 0.3])[0]
    goal = {"status": status}
    if status != "safe":
        goal["location"] = "অজানা" if rng.random() < 0.1 else rng.choice(UPAZILAS)
        if goal["location"] == "অজানা":
            goal["landmark"] = rng.choice(LANDMARKS)
        goal["household_size"] = rng.randint(1, 8)
        goal["vulnerable"] = rng.choices(VULNERABLE, weights=[2, 2, 1, 1, 4])[0]
        goal["can_travel"] = rng.random() > 0.3
    profile = {"verbosity": rng.choice([1, 2, 3])}
    return goal, profile


# ------------------------------------------------------ user simulator --
class UserSim:
    def __init__(self, goal, profile, rng):
        self.goal, self.profile, self.rng = goal, profile, rng
        self.agenda = [s for s in ("status", "location", "landmark", "household_size", "vulnerable")
                       if s in goal]
        rest = self.agenda[1:]
        rng.shuffle(rest)                            # status first; the rest in any order
        self.agenda = self.agenda[:1] + rest

    def _inform(self, k):
        out = []
        while self.agenda and len(out) < k:
            s = self.agenda.pop(0)
            out.append(("inform", s, self.goal[s]))
        return out

    def respond(self, sys_acts):
        a, s, _ = sys_acts[-1]
        if a == "request":
            if s in self.agenda:
                self.agenda.remove(s)
            return [("inform", s, self.goal[s])] + self._inform(self.profile["verbosity"] - 1)
        if a == "offer":
            return [("affirm", None, None)] if self.goal["can_travel"] else [("negate", "travel", None)]
        return [("thank_you", None, None), ("bye", None, None)]


# -------------------------------------------------------- system agent --
class SystemFSM:
    def __init__(self):
        self.state = {}

    def _priority(self):
        return "high" if self.state.get("vulnerable") not in (None, "নেই") else "normal"

    def act(self, user_acts):
        for a, s, v in user_acts:
            if a == "inform":
                self.state[s] = v
        last = user_acts[-1][0]
        if last == "bye":
            return [("bye", None, None)]
        if last == "affirm":
            return [("notify_success", "shelter", self.state["offered"])]
        if last == "negate":                      # cannot reach shelter -> becomes rescue
            self.state["status"] = "rescue"
        missing = [s for s in required_slots(self.state) if s not in self.state]
        if missing:
            return [("request", missing[0], None)]
        if self.state["status"] == "safe":
            return [("inform", "advice", "stay_alert")]
        if self.state["status"] == "rescue":
            return [("escalate_rescue", "priority", self._priority())]
        if self.state.get("location") == "অজানা":
            return [("escalate_officer", "reason", "location_unknown")]
        shelter = api_find_shelter(self.state.get("location"), self.state["household_size"])
        if shelter is None:
            return [("escalate_officer", "reason", "no_capacity")]
        self.state["offered"] = shelter
        return [("offer", "shelter", shelter)]


END_ACTS = ("bye", "escalate_rescue", "escalate_officer", "escalate_human")


def self_play(rng, max_turns=20):
    goal, profile = sample_scenario(rng)
    user, system = UserSim(goal, profile, rng), SystemFSM()
    turns = [("S", [("greeting", None, None), ("request", "status", None)])]
    u = user.respond(turns[0][1])
    while len(turns) < max_turns:
        turns.append(("U", u))
        s = system.act(u)
        turns.append(("S", s))
        if s[-1][0] in END_ACTS or u[-1][0] == "bye":
            break
        u = user.respond(s)
    if turns[-1][1][-1][0] != "bye":
        turns.append(("U", [("bye", None, None)]))
    return {"goal": goal, "profile": profile,
            "turns": [{"speaker": sp, "acts": [list(a) for a in acts]} for sp, acts in turns]}


def scripted_baseline(rng):
    """Happy path: rescue request, one slot per turn, always escalated."""
    turns = [("S", [("greeting", None, None), ("request", "status", None)]),
             ("U", [("inform", "status", "rescue")])]
    for s in ("location", "household_size", "vulnerable"):
        turns += [("S", [("request", s, None)]), ("U", [("inform", s, "x")])]
    turns += [("S", [("escalate_rescue", "priority", "normal")]), ("U", [("bye", None, None)])]
    return {"turns": [{"speaker": sp, "acts": [list(a) for a in acts]} for sp, acts in turns]}


if __name__ == "__main__":
    rng = random.Random(2026)
    outlines = [self_play(rng) for _ in range(1000)]
    with open("outlines.jsonl", "w", encoding="utf-8") as f:
        for o in outlines:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("wrote", len(outlines), "outlines")
