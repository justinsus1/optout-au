"""Gmail bridge for optout.py. Runs under the Hermes Python (has googleapiclient).

Reads one JSON request on stdin, prints one JSON result:
  {"action": "profile"}                                  -> {"email": ...}
  {"action": "draft", "to", "subject", "body"}           -> {"id": draft_id}
  {"action": "send",  "to", "subject", "body"}           -> {"id": message_id}
  {"action": "search", "q", "max"}                       -> [{"id","threadId","from","subject","date"}]
"""
import base64, json, os, sys
from email.mime.text import MIMEText

sys.path.insert(0, os.path.expanduser("~/.hermes/skills/productivity/google-workspace/scripts"))
from google_api import build_service  # noqa: E402


def _raw(req):
    m = MIMEText(req["body"], "plain", "utf-8")
    m["To"], m["Subject"] = req["to"], req["subject"]
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


def main():
    req = json.load(sys.stdin)
    g = build_service("gmail", "v1").users()
    act = req["action"]
    if act == "profile":
        out = {"email": g.getProfile(userId="me").execute()["emailAddress"]}
    elif act == "draft":
        r = g.drafts().create(userId="me", body={"message": {"raw": _raw(req)}}).execute()
        out = {"id": r["id"]}
    elif act == "send":
        r = g.messages().send(userId="me", body={"raw": _raw(req)}).execute()
        out = {"id": r["id"]}
    elif act == "search":
        res = g.messages().list(userId="me", q=req["q"], maxResults=req.get("max", 50)).execute()
        out = []
        for m in res.get("messages", []):
            full = g.messages().get(userId="me", id=m["id"], format="metadata",
                                    metadataHeaders=["From", "Subject", "Date"]).execute()
            h = {x["name"]: x["value"] for x in full["payload"]["headers"]}
            out.append({"id": m["id"], "threadId": m["threadId"], "from": h.get("From", ""),
                        "subject": h.get("Subject", ""), "date": h.get("Date", ""),
                        "ts": int(full.get("internalDate", 0)) // 1000,
                        "labels": full.get("labelIds", [])})
    else:
        sys.exit(f"unknown action {act}")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
