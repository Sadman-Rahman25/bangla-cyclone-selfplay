"""Persona stress test (idea E) for the cyclone and flood response line.

User dialogue acts are realised as text in one of four registers. The bot's
keyword NLU parses the text back into acts; understanding failures trigger a
re-prompt, and two consecutive failures hand the caller to a human operator.

Every register has separate *dev* and *test* phrasings. NLU v1 uses only the
standard-Bangla dev phrasings; NLU v2 adds the other registers' dev phrasings
and fuzzy matching. Both are evaluated on the held-out *test* phrasings.
"""
import collections
import random
import re
import unicodedata

from selfplay import SystemFSM, UserSim, api_find_shelter, sample_scenario

ROMAN = {"কয়রা": "Koyra", "শ্যামনগর": "Shyamnagar", "কলাপাড়া": "Kalapara",
         "হাতিয়া": "Hatiya", "কুতুবদিয়া": "Kutubdia"}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

# (dev phrasings, test phrasings) per register and act value.
T = {
 "standard": {
  "status:rescue": (["আমাদের উদ্ধার দরকার"], ["আমাদের এখনই উদ্ধার করুন", "পানি ঘরে ঢুকছে, আমাদের বাঁচান"]),
  "status:shelter": (["আশ্রয়কেন্দ্রে যেতে চাই"], ["আশ্রয় দরকার", "থাকার একটা জায়গা দরকার"]),
  "status:safe": (["আমরা নিরাপদ আছি"], ["আমরা নিরাপদে আছি", "আমরা ঠিক আছি"]),
  "loc": (["{u} উপজেলায় আছি"], ["আমরা {u}তে আছি", "{u}"]),
  "loc_unknown": (["জায়গার নাম জানি না"], ["ঠিক কোথায় আছি জানি না"]),
  "landmark": (["{l}"], ["{l} আছি"]),
  "size": (["{n} জন"], ["আমরা মোট {n} জন"]),
  "vul:বয়স্ক": (["একজন বয়স্ক মানুষ আছেন"], ["বয়স্ক বাবা সাথে আছেন", "বৃদ্ধ মা সাথে আছেন"]),
  "vul:শিশু": (["ছোট শিশু আছে"], ["শিশু আছে একটা", "ছোট বাচ্চা আছে"]),
  "vul:অন্তঃসত্ত্বা": (["একজন অন্তঃসত্ত্বা মা আছেন"], ["স্ত্রী অন্তঃসত্ত্বা", "আমার স্ত্রী গর্ভবতী"]),
  "vul:প্রতিবন্ধী": (["একজন প্রতিবন্ধী মানুষ আছেন"], ["প্রতিবন্ধী ভাই আছে", "একজন হাঁটতে পারেন না"]),
  "vul:নেই": (["না, কেউ নেই"], ["কেউ নেই", "সবাই সুস্থ আছে"]),
  "affirm": (["হ্যাঁ, যাব"], ["হ্যাঁ যাব", "ঠিক আছে, আসছি"]),
  "negate": (["যেতে পারব না"], ["পারব না যেতে", "ওখানে যাওয়া সম্ভব না"]),
 },
 "banglish": {
  "status:rescue": (["amader uddhar dorkar"], ["uddhar koren please", "pani ghore dhukche, amader bachan"]),
  "status:shelter": (["ashroykendro te jete chai"], ["ashroy dorkar", "thakar jayga dorkar"]),
  "status:safe": (["amra nirapod achi"], ["amra nirapode", "amra thik achi"]),
  "loc": (["{r} upazila te achi"], ["amra {r} te", "{r}"]),
  "loc_unknown": (["jaygar nam jani na"], ["kothay achi jani na"]),
  "landmark": (["{lr}"], ["{lr} achi"]),
  "size": (["{n} jon"], ["total {n} jon"]),
  "vul:বয়স্ক": (["ekjon boyosko manush ache"], ["boyosko baba ache", "briddho ma ache"]),
  "vul:শিশু": (["choto shishu ache"], ["shishu ache", "choto baccha ache"]),
  "vul:অন্তঃসত্ত্বা": (["ekjon ontosotta ma ache"], ["wife ontosotta", "wife pregnant"]),
  "vul:প্রতিবন্ধী": (["ekjon protibondhi manush ache"], ["protibondhi bhai ache", "ekjon hatte pare na"]),
  "vul:নেই": (["na, keu nai"], ["keu nai", "sobai thik ache"]),
  "affirm": (["ha jabo"], ["ha", "ok ashchi"]),
  "negate": (["jete parbo na"], ["parbo na", "jawa possible na"]),
 },
 "sylheti_style": {   # approximate forms; to be replaced by native-speaker paraphrases
  "status:rescue": (["আমরারে উদ্ধার করইন"], ["উদ্ধার করইন তাড়াতাড়ি", "ফানি উঠি গেছে, আমরারে বাঁচাইন"]),
  "status:shelter": (["আশ্রয়কেন্দ্রো যাইতাম চাই"], ["আশ্রয় লাগবো", "থাকার জাগা লাগবো"]),
  "status:safe": (["আমরা ভালা আছি"], ["ভালা আছি আমরা", "কুনু সমস্যা নাই"]),
  "loc": (["{u}ত আছি"], ["আমরা {u}ত", "{u}"]),
  "loc_unknown": (["জাগার নাম জানি না"], ["কই আছি জানি না"]),
  "landmark": (["{l}"], ["{l} আছি"]),
  "size": (["{n} জন"], ["{n} জন মানুষ"]),
  "vul:বয়স্ক": (["এক বুড়া মানুষ আছইন"], ["বুড়া মা সাথে আছইন", "বয়স্ক বাবা আছইন"]),
  "vul:শিশু": (["ছোট বাচ্চা আছে"], ["বাচ্চা আছে", "ছোট ফুয়া আছে"]),
  "vul:অন্তঃসত্ত্বা": (["একজন অন্তঃসত্ত্বা মা আছইন"], ["বউ অন্তঃসত্ত্বা", "বউ গর্ভবতী"]),
  "vul:প্রতিবন্ধী": (["একজন প্রতিবন্ধী আছইন"], ["প্রতিবন্ধী ভাই আছইন", "একজন চলতে পারইন না"]),
  "vul:নেই": (["না, কেউ নাই"], ["কেউ নাই", "হকলে ভালা আছি"]),
  "affirm": (["অয়, যাইমু"], ["অয়", "ঠিক আছে, যাইমু"]),
  "negate": (["যাইতাম পারতাম নায়"], ["পারতাম নায়", "যাওয়া যাইতো নায়"]),
 },
 "noisy": {   # panic and ASR-like errors: repetition, dropped or misspelt characters
  "status:rescue": (["উদ্দার উদ্দার দরকার তাড়াতাড়ি"], ["উদ্ধর করেন প্লিজ", "উধার দরকার"]),
  "status:shelter": (["আশ্রয় কেন্দ্র যাব"], ["আশ্রয়ো দরকার", "আশ্রয় আশ্রয়"]),
  "status:safe": (["নিরাপদ নিরাপদ আছি"], ["নিরাপট আছি", "ঠিক আসি"]),
  "loc": (["{c} উপজেলা"], ["{c}তে", "{c}"]),
  "loc_unknown": (["জানি না জানি না"], ["জানিনা কোথায়"]),
  "landmark": (["{l}"], ["{l}"]),
  "size": (["{n}... {n} জন"], ["মোট {n}জন"]),
  "vul:বয়স্ক": (["বয়স্ক... বয়স্ক একজন"], ["বয়ষ্ক আছেন", "বয়স্ক আসেন"]),
  "vul:শিশু": (["শিশু আছে শিশু"], ["শিসু আছে", "শিশু আসে"]),
  "vul:অন্তঃসত্ত্বা": (["অন্তঃসত্তা মা"], ["অন্তসত্ত্বা", "অন্তঃসত্ত্বা মা আসে"]),
  "vul:প্রতিবন্ধী": (["প্রতিবন্দী আছে"], ["প্রতিবন্ধি", "প্রতিবন্ধী আসে"]),
  "vul:নেই": (["কেউ নাই কেউ নাই"], ["না নাই কেউ", "কেউ নেই"]),
  "affirm": (["হা যাব"], ["হ্যা যাবো", "হা হা"]),
  "negate": (["পারব না যেতে"], ["পারবো না", "যাওয়া যাবে না"]),
 },
}
LANDMARK_ROMAN = {"বড় মসজিদের পাশে": "boro masjid er pashe",
                  "প্রাইমারি স্কুলের কাছে": "primary school er kache",
                  "বাজারের পাশে": "bazar er pashe"}


def corrupt(word, rng):
    """Drop one internal character, simulating an ASR or typing error."""
    if len(word) < 4:
        return word
    i = rng.randrange(1, len(word) - 1)
    return word[:i] + word[i + 1:]


def realise(act, reg, split, rng):
    a, s, v = act
    pick = lambda key: rng.choice(T[reg][key][0 if split == "dev" else 1])
    if a == "inform" and s == "status":
        return pick(f"status:{v}")
    if a == "inform" and s == "location":
        if v == "অজানা":
            return pick("loc_unknown")
        return pick("loc").format(u=v, r=ROMAN[v], c=corrupt(v, rng))
    if a == "inform" and s == "landmark":
        return pick("landmark").format(l=v, lr=LANDMARK_ROMAN[v])
    if a == "inform" and s == "household_size":
        n = str(v) if reg == "banglish" else str(v).translate(BN_DIGITS)
        return pick("size").format(n=n)
    if a == "inform" and s == "vulnerable":
        return pick(f"vul:{v}")
    if a in ("affirm", "negate"):
        return pick(a)
    return ""


# --------------------------------------------------------------- NLU --
def lexicon(version):
    lex = {
        "status": {"rescue": ["উদ্ধার"], "shelter": ["আশ্রয়"], "safe": ["নিরাপদ"]},
        "unknown": ["জানি না"],
        "landmark": ["পাশে", "কাছে"],
        "vulnerable": {"বয়স্ক": ["বয়স্ক"], "শিশু": ["শিশু"], "অন্তঃসত্ত্বা": ["অন্তঃসত্ত্বা"],
                       "প্রতিবন্ধী": ["প্রতিবন্ধী"], "নেই": ["কেউ নেই"]},
        "affirm": ["হ্যাঁ"], "negate": ["পারব না"],
        "places": {u: [u] for u in ROMAN},
    }
    if version == 2:     # additions derived only from the other registers' DEV phrasings
        lex["status"]["rescue"] += ["uddhar", "উদ্দার"]
        lex["status"]["shelter"] += ["ashroy"]
        lex["status"]["safe"] += ["nirapod", "ভালা"]
        lex["unknown"] += ["jani na"]
        lex["landmark"] += ["pashe", "kache"]
        lex["vulnerable"]["বয়স্ক"] += ["boyosko", "বুড়া"]
        lex["vulnerable"]["শিশু"] += ["shishu", "বাচ্চা"]
        lex["vulnerable"]["অন্তঃসত্ত্বা"] += ["ontosotta"]
        lex["vulnerable"]["প্রতিবন্ধী"] += ["protibondhi"]
        lex["vulnerable"]["নেই"] += ["keu nai", "কেউ নাই"]
        lex["affirm"] += ["ha", "অয়", "হা"]
        lex["negate"] += ["parbo na", "পারতাম নায়"]
        for u, r in ROMAN.items():
            lex["places"][u].append(r.lower())
    return lex


def _lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _has(text, key, fuzzy):
    toks = re.findall(r"[^\s,।.!?…]+", text)
    if " " in key or len(key) <= 3:                  # phrases and short words: exact
        return key in text if " " in key else key in toks
    if key in text:
        return True
    return fuzzy and any(abs(len(t) - len(key)) <= 1 and _lev(t, key) <= 1 for t in toks)


def parse(text, expected, version):
    """Return the dialogue acts understood from `text`."""
    text = unicodedata.normalize("NFC", text).lower()
    lex, fuzzy, acts = lexicon(version), version == 2, []
    if expected == "offer":
        if any(_has(text, k, fuzzy) for k in lex["negate"]):
            return [("negate", "travel", None)]
        if any(_has(text, k, fuzzy) for k in lex["affirm"]):
            return [("affirm", None, None)]
        return []
    for val, keys in lex["status"].items():
        if any(_has(text, k, fuzzy) for k in keys):
            acts.append(("inform", "status", val)); break
    if any(_has(text, k, fuzzy) for k in lex["unknown"]):
        acts.append(("inform", "location", "অজানা"))
    else:
        for u, keys in lex["places"].items():
            if any(_has(text, k.lower(), fuzzy) for k in keys):
                acts.append(("inform", "location", u)); break
    if expected == "landmark" and any(_has(text, k, fuzzy) for k in lex["landmark"]):
        acts.append(("inform", "landmark", text))
    m = re.search(r"[0-9০-৯]+", text)
    if m:
        acts.append(("inform", "household_size", int(m.group().translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")))))
    for val, keys in lex["vulnerable"].items():
        if any(_has(text, k, fuzzy) for k in keys):
            acts.append(("inform", "vulnerable", val)); break
    return acts


# ------------------------------------------------------------- dialogue --
def expected_outcome(g):
    if g["status"] == "safe":
        return ("safe_advice",)
    pri = "high" if g["vulnerable"] != "নেই" else "normal"
    if g["status"] == "rescue":
        return ("rescue", g["location"], g["household_size"], pri)
    if g["location"] == "অজানা":
        return ("officer_location_unknown",)
    shelter = api_find_shelter(g["location"], g["household_size"])
    if shelter is None:
        return ("officer_no_capacity",)
    return ("shelter", shelter) if g["can_travel"] else ("rescue", g["location"], g["household_size"], pri)


def run_dialogue(rng, reg, version, split="test", max_turns=24):
    goal, profile = sample_scenario(rng)
    user, system = UserSim(goal, profile, rng), SystemFSM()
    sys_acts, expected, fails, turns = [("request", "status", None)], "status", 0, 0
    while turns < max_turns:
        turns += 1
        u_acts = user.respond(sys_acts) if sys_acts[-1][0] != "repeat" else \
                 ([("inform", expected, goal[expected])] if expected != "offer"
                  else ([("affirm", None, None)] if goal["can_travel"] else [("negate", "travel", None)]))
        text = " , ".join(realise(a, reg, split, rng) for a in u_acts if a[0] in ("inform", "affirm", "negate"))
        if u_acts[-1][0] == "bye":
            break
        parsed = parse(text, expected, version)
        got_expected = any(a[0] in ("affirm", "negate") for a in parsed) if expected == "offer" \
                       else any(a[1] == expected for a in parsed)
        if not got_expected:
            fails += 1
            if fails >= 2:
                return "handoff", turns
            for a in parsed:                       # keep other slots understood, if still empty
                if a[0] == "inform" and a[1] not in system.state:
                    system.state[a[1]] = a[2]
            sys_acts = [("repeat", expected, None)]
            continue
        fails = 0
        # fill only the requested slot and slots still empty; never overwrite
        parsed = [a for a in parsed if a[0] != "inform" or a[1] == expected or a[1] not in system.state]
        sys_acts = system.act(parsed)
        a, s, v = sys_acts[-1]
        if a == "request":
            expected = s
        elif a == "offer":
            expected = "offer"
        else:
            break
    st, (a, s, v) = system.state, sys_acts[-1]
    if a == "inform":
        got = ("safe_advice",)
    elif a == "escalate_rescue":
        got = ("rescue", st.get("location"), st.get("household_size"), v)
    elif a == "escalate_officer":
        got = ("officer_location_unknown",) if v == "location_unknown" else ("officer_no_capacity",)
    elif a == "notify_success":
        got = ("shelter", v)
    else:
        return "incomplete", turns
    return ("correct" if got == expected_outcome(goal) else "wrong"), turns


def evaluate(version, split="test", n=400, seed=2026):
    rows = {}
    for reg in T:
        rng = random.Random(seed)
        res = [run_dialogue(rng, reg, version, split) for _ in range(n)]
        c = collections.Counter(r for r, _ in res)
        rows[reg] = {k: c[k] / n for k in ("correct", "handoff", "wrong", "incomplete")}
        rows[reg]["turns"] = sum(t for _, t in res) / n
    return rows


if __name__ == "__main__":
    for split in ("dev", "test"):
        for version in (1, 2):
            rows = evaluate(version, split)
            print(f"\nNLU v{version} on {split.upper()} phrasings (400 dialogues per persona)")
            print(f"  {'persona':<15}{'correct':>9}{'handoff':>9}{'wrong':>8}{'incompl':>9}{'turns':>7}")
            for reg, r in rows.items():
                print(f"  {reg:<15}{r['correct']:>9.1%}{r['handoff']:>9.1%}{r['wrong']:>8.1%}{r['incomplete']:>9.1%}{r['turns']:>7.1f}")
            vals = [r["correct"] for r in rows.values()]
            print(f"  fairness gap (max - min correct): {max(vals) - min(vals):.1%}")
