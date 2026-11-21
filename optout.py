#!/usr/bin/env python3
"""optout: get your details out of data brokers, Australian-style.

A free, local alternative to Optery/DeleteMe for Australian residents. It sends
requests under the Privacy Act 1988 (Cth) (APP 6, 7, 11, 12), tracks replies in
Gmail, and puts follow-up TODOs in ~/org/refile.org.

  optout setup                 save your details (asked interactively)
  optout list [--group G]      brokers and where each request is at
  optout scan [--open]         Google searches that show if people-search sites list you
  optout request [IDS] [--group G | --all] [--access] [--send] [--dry-run]
                               create Gmail drafts (default) or send directly
  optout forms [IDS] [--open]  brokers that need a web form (open them, then `optout done ID`)
  optout done ID [ID...]       mark a form/manual opt-out as finished
  optout reset ID [ID...]      forget a broker's status
  optout sync                  check Gmail: sent? replied? add org follow-ups
  optout status                summary + what needs attention
  optout followup ID [--send]  draft a 30-day reminder that warns of an OAIC complaint

Groups: people (people-search), marketing, register (official opt-out lists), b2b
(work-contact databases; skipped unless asked).
Env (testing): OPTOUT_STATE (state dir), OPTOUT_ORG (org file for follow-ups).
"""
import argparse, datetime as dt, glob, json, os, re, subprocess, sys, urllib.parse, webbrowser

HERE = os.path.dirname(os.path.realpath(__file__))
BROKERS_FILE = os.path.join(HERE, "brokers.json")
HELPER = os.path.join(HERE, "gmail_helper.py")
STATE_DIR = os.environ.get("OPTOUT_STATE", os.path.expanduser("~/.hermes/state/broker_optout"))
PROFILE_FILE = os.path.join(STATE_DIR, "profile.json")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
ORG_FILE = os.environ.get("OPTOUT_ORG", os.path.expanduser("~/org/refile.org"))
DEFAULT_GROUPS = ("people", "marketing")
WAIT_DAYS = 30
OAIC_URL = "https://www.oaic.gov.au/privacy/privacy-complaints/lodge-a-privacy-complaint-with-us"


# ---------- storage ----------

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def brokers():
    return load_json(BROKERS_FILE, {})["brokers"]


def by_id():
    return {b["id"]: b for b in brokers()}


def state():
    return load_json(STATE_FILE, {"brokers": {}})


def profile():
    p = load_json(PROFILE_FILE, None)
    if not p:
        sys.exit("No profile yet. Run: optout setup")
    return p


def today():
    return dt.date.today()


def ref(bid):
    return "PRIV-" + re.sub(r"[^A-Z0-9]", "", bid.upper())


def domain(email):
    return email.split("@", 1)[1].lower() if email and "@" in email else None


# ---------- gmail bridge ----------

def hermes_python():
    cands = [os.environ.get("OPTOUT_PYTHON", "")]
    cands += sorted(glob.glob(os.path.expanduser("~/.hermes/installs/*/environments/*/venv/bin/python3")),
                    key=os.path.getmtime, reverse=True)
    cands.append(sys.executable)
    for py in cands:
        if py and os.path.exists(py) and subprocess.run(
                [py, "-c", "import googleapiclient"], capture_output=True).returncode == 0:
            return py
    sys.exit("Can't find a Python with the Google API client. Is the google-workspace skill set up?")


_PY = None


def gmail(action, **kw):
    global _PY
    _PY = _PY or hermes_python()
    r = subprocess.run([_PY, HELPER], input=json.dumps({"action": action, **kw}),
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        sys.exit(f"Gmail error: {(r.stderr or r.stdout).strip()[-600:]}")
    return json.loads(r.stdout)


# ---------- letters ----------

def details_block(p):
    rows = [("Name", p["name"])]
    if p.get("other_names"):
        rows.append(("Other names", ", ".join(p["other_names"])))
    rows.append(("Email", ", ".join(p["emails"])))
    if p.get("phone"):
        rows.append(("Phone", p["phone"]))
    if p.get("location"):
        rows.append(("Suburb/State", p["location"]))
    return "\n".join(f"  {k}: {v}" for k, v in rows)


def request_letter(b, p, access=False):
    asks = [
        "Stop using or disclosing my personal information for direct marketing, and stop using it "
        "to help other organisations direct-market to me (APP 7.6(a) and (b)).",
        "Tell me where you got my personal information (APP 7.6(e)).",
        "Destroy or de-identify all personal information you hold about me, because you have no "
        "lawful need to keep it (APP 11.2), and stop disclosing it to anyone else (APP 6). You may "
        "keep only the minimum needed to stop my details being collected again. If you believe you "
        "must keep anything else, tell me what it is and the legal reason.",
    ]
    if access:
        asks.insert(0, "Before deleting, give me a copy of the personal information you hold about me "
                       "and tell me who you have disclosed it to (APP 12).")
    asks.append(f"Confirm in writing, within {WAIT_DAYS} days, what you have done.")
    numbered = "\n\n".join(f"{i}. {a}" for i, a in enumerate(asks, 1))
    minor = "\nI am under 18 years of age.\n" if p.get("minor") else ""
    body = f"""Dear Privacy Officer,

I am writing to {b['name']} with requests under the Privacy Act 1988 (Cth) and the Australian Privacy Principles (APPs) about any personal information you hold about me.

These details are to help you find my records. Please use them only to action this request:
{details_block(p)}
{minor}
I ask that you:

{numbered}

Please note:
- An organisation that trades in personal information is covered by the Privacy Act whatever its annual turnover (s 6D(4)(c) and (d)), so the small business exemption does not apply.
- If you are based outside Australia, the Act still applies to you if you carry on business in Australia (s 5B).
- I will not send identity documents. The details above should be enough to find my records. If you need anything more, tell me exactly what and why.

If I do not get a satisfactory reply within {WAIT_DAYS} days, I intend to lodge a complaint with the Office of the Australian Information Commissioner (OAIC).

Kind regards,
{p['name']}
"""
    subject = f"Privacy Act request: delete my information and stop direct marketing [Ref {ref(b['id'])}]"
    return subject, body


def followup_letter(b, p, sent_on):
    body = f"""Dear Privacy Officer,

On {sent_on} I asked {b['name']} under the Privacy Act 1988 (Cth) to stop using my personal information for direct marketing, to tell me its source (APP 7.6), and to destroy or de-identify it (APP 11.2). It has now been more than {WAIT_DAYS} days and I have not received a satisfactory response.

My details again:
{details_block(p)}

Please action my request and confirm in writing within 14 days. If you do not, I will lodge a complaint with the Office of the Australian Information Commissioner ({OAIC_URL}).

Kind regards,
{p['name']}
"""
    subject = f"Follow-up: Privacy Act request not yet actioned [Ref {ref(b['id'])}]"
    return subject, body


# ---------- commands ----------

def ask(prompt, default=""):
    v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return v or default


def cmd_setup(a):
    old = load_json(PROFILE_FILE, {}) or {}
    print("Only give what you want brokers to match on. Less is fine; name + email is the minimum.\n")
    try:
        gmail_addr = gmail("profile")["email"]
    except SystemExit:
        gmail_addr = ""
    name = a.name or ask("Full name", old.get("name", ""))
    others = a.other_names if a.other_names is not None else ask(
        "Other names/spellings (comma separated, optional)", ", ".join(old.get("other_names", [])))
    emails = a.emails if a.emails is not None else ask(
        "Email addresses to remove (comma separated)", ", ".join(old.get("emails", [])) or gmail_addr)
    phone = a.phone if a.phone is not None else ask("Mobile number (optional)", old.get("phone", ""))
    loc = a.location if a.location is not None else ask("Suburb and state, e.g. Epping NSW (optional)",
                                                         old.get("location", ""))
    if a.minor is None:
        minor = ask("Say in the letter that you're under 18? (y/n)", "y" if old.get("minor") else "n").lower() == "y"
    else:
        minor = a.minor
    split = lambda s: [x.strip() for x in s.split(",") if x.strip()] if isinstance(s, str) else s
    p = {"name": name, "other_names": split(others), "emails": split(emails), "phone": phone,
         "location": loc, "minor": minor}
    if not p["name"] or not p["emails"]:
        sys.exit("Name and at least one email are required.")
    save_json(PROFILE_FILE, p, private=True)
    print(f"\nSaved to {PROFILE_FILE} (only you can read it). Next: optout scan, then optout request")


def status_of(st, bid):
    return st["brokers"].get(bid, {}).get("status", "-")


def select(a, need):
    """Brokers chosen by IDs/--group/--all, filtered to those having `need` (email|form)."""
    bmap = by_id()
    if a.ids:
        bad = [i for i in a.ids if i not in bmap]
        if bad:
            sys.exit(f"Unknown broker id(s): {', '.join(bad)}. See: optout list")
        chosen = [bmap[i] for i in a.ids]
    elif getattr(a, "all", False):
        chosen = brokers()
    else:
        groups = [a.group] if a.group else list(DEFAULT_GROUPS) + (["register"] if need == "form" else [])
        chosen = [b for b in brokers() if b["group"] in groups]
    return [b for b in chosen if b.get(need)]


def cmd_list(a):
    st = state()
    print(f"{'id':16} {'group':9} {'AU':2}  {'how':10} {'status':10} name")
    for b in brokers():
        if a.group and b["group"] != a.group:
            continue
        how = "+".join(x for x in ("email", "form") if b.get(x))
        print(f"{b['id']:16} {b['group']:9} {'y' if b['au'] else ' ':2}  {how:10} {status_of(st, b['id']):10} {b['name']}")


def cmd_scan(a):
    p = profile()
    names = [p["name"]] + p.get("other_names", [])
    sites = [b["site"] for b in brokers() if b.get("site")]
    qs = []
    for n in names:
        qs.append((f'"{n}" people-search sites', f'"{n}" ' + " OR ".join(f"site:{s}" for s in sites[:8])))
        qs.append((f'"{n}" more sites', f'"{n}" ' + " OR ".join(f"site:{s}" for s in sites[8:])))
        if p.get("location"):
            qs.append((f'"{n}" + location', f'"{n}" "{p["location"].split()[0]}"'))
    for e in p["emails"]:
        qs.append((f'email {e}', f'"{e}"'))
    if p.get("phone"):
        digits = re.sub(r"\D", "", p["phone"])
        qs.append(("phone", f'"{p["phone"]}" OR "{digits}"'))
    print("Open these and look for pages that list your details (address, phone, age, relatives).\n"
          "Results that are just you on school/sport sites aren't brokers; ignore them.\n")
    for label, q in qs:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(q)
        print(f"- {label}\n  {url}")
        if a.open:
            webbrowser.open_new_tab(url)
    print("\nFound a profile on a site with a form (Radaris, PersonLookup...)? run: optout forms --open")


def cmd_request(a):
    p, st = profile(), state()
    targets = select(a, "email")
    if not a.force:
        skipped = [b["id"] for b in targets if status_of(st, b["id"]) not in ("-", "")]
        targets = [b for b in targets if b["id"] not in skipped]
        if skipped:
            print(f"Already handled (use --force to redo): {', '.join(skipped)}")
    if not targets:
        print("Nothing to send.")
        return
    if a.dry_run:
        for b in targets:
            s, body = request_letter(b, p, a.access)
            print(f"===== To: {b['email']}\nSubject: {s}\n\n{body}")
        print(f"(dry run: {len(targets)} letters, nothing created)")
        return
    if a.send:
        print("About to SEND (not draft) to:\n  " + "\n  ".join(f"{b['name']} <{b['email']}>" for b in targets))
        if input("Type 'send' to confirm: ").strip().lower() != "send":
            sys.exit("Cancelled.")
    for b in targets:
        s, body = request_letter(b, p, a.access)
        r = gmail("send" if a.send else "draft", to=b["email"], subject=s, body=body)
        rec = st["brokers"].setdefault(b["id"], {})
        rec.update({"status": "sent" if a.send else "drafted", "ref": ref(b["id"]), "to": b["email"],
                    "drafted_at" if not a.send else "sent_at": today().isoformat(),
                    "draft_id" if not a.send else "message_id": r["id"]})
        save_json(STATE_FILE, st)
        print(f"{'sent' if a.send else 'drafted'}: {b['name']} <{b['email']}>")
    if not a.send:
        print("\nReview them in Gmail > Drafts (https://mail.google.com/mail/u/0/#drafts) and press Send.\n"
              "Then run `optout sync` (or wait for it to run) to start the 30-day clock.")
    else:
        add_org_followups(st)


def cmd_forms(a):
    st = state()
    # Brokers already handled by email don't need the form too.
    todo = [b for b in select(a, "form") if status_of(st, b["id"]) in ("-", "")]
    if not todo:
        print("No form opt-outs left.")
        return
    for b in todo:
        print(f"- {b['id']:16} {b['name']}\n    {b['form']}" + (f"\n    note: {b['notes']}" if b.get("notes") else ""))
        if a.open:
            webbrowser.open_new_tab(b["form"])
    print("\nAfter finishing one: optout done ID   (sites with both a form and email can use either)")


def cmd_done(a):
    st, bmap = state(), by_id()
    for i in a.ids:
        if i not in bmap:
            sys.exit(f"Unknown broker id: {i}")
        st["brokers"].setdefault(i, {}).update({"status": "done", "done_at": today().isoformat()})
        print(f"done: {bmap[i]['name']}")
    save_json(STATE_FILE, st)


def cmd_reset(a):
    st = state()
    for i in a.ids:
        st["brokers"].pop(i, None)
    save_json(STATE_FILE, st)
    print("reset:", ", ".join(a.ids))


def cmd_sync(a):
    st, bmap = state(), by_id()
    changed = []
    for bid, rec in st["brokers"].items():
        if rec.get("status") not in ("drafted", "sent", "followed_up"):
            continue
        r = rec.get("ref") or ref(bid)
        if rec["status"] == "drafted":
            hits = gmail("search", q=f'in:sent subject:"{r}"', max=5)
            if hits:
                first = min(hits, key=lambda h: h["ts"])
                rec.update({"status": "sent", "sent_at": dt.date.fromtimestamp(first["ts"]).isoformat()})
                changed.append(f"sent: {bmap.get(bid, {}).get('name', bid)}")
        if rec.get("status") in ("sent", "followed_up"):
            dom = domain(rec.get("to"))
            q = f'-in:sent -in:drafts ({{subject:"{r}"' + (f" from:{dom}" if dom else "") + "})" \
                f" after:{rec['sent_at'].replace('-', '/')}"
            replies = [h for h in gmail("search", q=q, max=10) if "DRAFT" not in h["labels"]]
            if replies:
                last = max(replies, key=lambda h: h["ts"])
                rec.update({"status": "replied", "replied_at": dt.date.fromtimestamp(last["ts"]).isoformat(),
                            "reply_subject": last["subject"], "reply_from": last["from"]})
                changed.append(f"replied: {bmap.get(bid, {}).get('name', bid)} - {last['subject'][:70]}")
    save_json(STATE_FILE, st)
    added = add_org_followups(st)
    for c in changed + added:
        print(c)


def add_org_followups(st):
    """One TODO per sent request (deadline = sent + 30d) in the org inbox, deduped by :OPTOUT_ID:."""
    bmap = by_id()
    try:
        existing = open(ORG_FILE).read()
    except FileNotFoundError:
        existing = ""
    new, out = [], []
    for bid, rec in st["brokers"].items():
        if rec.get("status") != "sent" or f":OPTOUT_ID: {bid}\n" in existing:
            continue
        due = dt.date.fromisoformat(rec["sent_at"]) + dt.timedelta(days=WAIT_DAYS)
        name = bmap.get(bid, {}).get("name", bid)
        q = urllib.parse.quote(f'"{rec.get("ref", ref(bid))}"')
        new.append(f"""* TODO Check privacy reply from {name} :privacy:
DEADLINE: <{due.isoformat()} {due.strftime('%a')}>
:PROPERTIES:
:OPTOUT_ID: {bid}
:END:
Sent {rec['sent_at']}. If no proper reply by the deadline: =optout followup {bid}=, then complain to the OAIC.
[[https://mail.google.com/mail/u/0/#search/{q}][Gmail thread]]
""")
        out.append(f"org: follow-up for {name} due {due.isoformat()}")
    if new:
        with open(ORG_FILE, "a") as f:
            f.write(("" if existing.endswith("\n") or not existing else "\n") + "\n".join(new))
    return out


def cmd_status(a):
    st, bmap = state(), by_id()
    recs = st["brokers"]
    counts = {}
    for r in recs.values():
        counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
    print("Requests:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none yet")
    overdue = [(bid, r) for bid, r in recs.items() if r.get("status") == "sent"
               and today() - dt.date.fromisoformat(r["sent_at"]) > dt.timedelta(days=WAIT_DAYS)]
    drafted = [bid for bid, r in recs.items() if r.get("status") == "drafted"]
    replied = [(bid, r) for bid, r in recs.items() if r.get("status") == "replied"]
    left_email = [b for b in brokers() if b["group"] in DEFAULT_GROUPS and b.get("email") and b["id"] not in recs]
    left_form = [b for b in brokers() if b["group"] in DEFAULT_GROUPS + ("register",) and b.get("form")
                 and not b.get("email") and status_of(st, b["id"]) != "done"]
    if drafted:
        print(f"\nDrafts not sent yet ({len(drafted)}): {', '.join(drafted)}  -> Gmail Drafts, then optout sync")
    if replied:
        print("\nReplies to read (then `optout done ID` if they complied):")
        for bid, r in replied:
            print(f"  {bid}: {r.get('reply_subject', '')[:70]}  ({r.get('replied_at')})")
    if overdue:
        print(f"\nNo reply after {WAIT_DAYS} days: " + ", ".join(b for b, _ in overdue) + "  -> optout followup ID")
    if left_email:
        print(f"\nNot contacted yet by email ({len(left_email)}): optout request")
    if left_form:
        print(f"Web-form opt-outs left ({len(left_form)}): optout forms --open")


def cmd_followup(a):
    p, st, bmap = profile(), state(), by_id()
    b = bmap.get(a.id) or sys.exit(f"Unknown broker id: {a.id}")
    rec = st["brokers"].get(a.id, {})
    if not rec.get("sent_at") or not b.get("email"):
        sys.exit("No sent email request on record for that broker.")
    s, body = followup_letter(b, p, rec["sent_at"])
    if a.dry_run:
        print(f"To: {b['email']}\nSubject: {s}\n\n{body}")
        return
    if a.send and input(f"Send follow-up to {b['email']}? Type 'send': ").strip().lower() != "send":
        sys.exit("Cancelled.")
    gmail("send" if a.send else "draft", to=b["email"], subject=s, body=body)
    rec.update({"status": "followed_up", "followup_at": today().isoformat()})
    save_json(STATE_FILE, st)
    print(("Sent" if a.send else "Drafted") + f" follow-up to {b['name']}. If still nothing in 14 days: {OAIC_URL}")


def main():
    ap = argparse.ArgumentParser(prog="optout", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    for f in ("name", "phone", "location"):
        s.add_argument(f"--{f}")
    s.add_argument("--other-names", dest="other_names")
    s.add_argument("--emails")
    s.add_argument("--minor", action=argparse.BooleanOptionalAction, default=None)
    s = sub.add_parser("list"); s.add_argument("--group")
    s = sub.add_parser("scan"); s.add_argument("--open", action="store_true")
    s = sub.add_parser("request"); s.add_argument("ids", nargs="*"); s.add_argument("--group")
    s.add_argument("--all", action="store_true"); s.add_argument("--access", action="store_true")
    s.add_argument("--send", action="store_true"); s.add_argument("--dry-run", action="store_true")
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("forms"); s.add_argument("ids", nargs="*"); s.add_argument("--group")
    s.add_argument("--all", action="store_true"); s.add_argument("--open", action="store_true")
    s = sub.add_parser("done"); s.add_argument("ids", nargs="+")
    s = sub.add_parser("reset"); s.add_argument("ids", nargs="+")
    sub.add_parser("sync"); sub.add_parser("status")
    s = sub.add_parser("followup"); s.add_argument("id"); s.add_argument("--send", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"setup": cmd_setup, "list": cmd_list, "scan": cmd_scan, "request": cmd_request, "forms": cmd_forms,
     "done": cmd_done, "reset": cmd_reset, "sync": cmd_sync, "status": cmd_status,
     "followup": cmd_followup}[a.cmd](a)


if __name__ == "__main__":
    main()
