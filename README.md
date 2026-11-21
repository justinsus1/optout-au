# optout-au

A free, local alternative to Optery / DeleteMe for **Australian residents**.

It sends data brokers requests under the *Privacy Act 1988* (Cth), tracks the replies in Gmail, and reminds you to follow up after 30 days.

## What the requests ask for

- Stop using or disclosing your details for direct marketing, and say where they got them (**APP 7.6**)
- Destroy or de-identify your details (**APP 11.2**) and stop passing them on (**APP 6**)
- Optionally (`--access`), give you a copy first (**APP 12**)
- They point out that the small business exemption does not cover businesses that trade in personal information (**s 6D(4)(c)–(d)**), and that overseas brokers doing business in Australia are covered (**s 5B**)
- They refuse to send identity documents, and warn of an **OAIC** complaint if the broker hasn't replied within 30 days

Australia has no GDPR-style right to erasure, so the deletion part is a strongly worded request rather than a hard right. The direct-marketing opt-out (APP 7) is enforceable.

## Brokers

`brokers.json` has 32 entries, each recording where its contact details came from. They are grouped as:

| group | what | default |
|---|---|---|
| `people` | people-search sites (PersonLookup, ReverseAustralia, Radaris AU, InfoTracer AU…) | yes |
| `marketing` | consumer marketing data (Acxiom AU, illion, Quantium, LiveRamp AU, Australia Post…) | yes |
| `register` | official opt-out lists (Do Not Call, Equifax Do Not Contact, Google "Results about you") | forms only |
| `b2b` | work-contact databases (ZoomInfo, Apollo, RocketReach…) | no, ask with `--group b2b` |

Brokers that only take a web form are opened in your browser, and you mark each one done.

## Usage

```
optout setup                 # name + email minimum; phone/suburb optional
optout scan --open           # Google searches showing whether people-search sites list you
optout request --dry-run     # preview the letters
optout request               # create Gmail drafts (review, then send them yourself)
optout request --send        # or send directly (asks for confirmation)
optout forms --open          # web-form opt-outs; then: optout done ID
optout sync                  # detect sent requests and replies; add org-mode follow-ups
optout status                # what needs attention
optout followup ID           # 30-day reminder letter
```

## Requirements

- Python 3.11+ (the core script uses only the standard library)
- Gmail access through the [Hermes Agent](https://github.com/NousResearch/hermes-agent) `google-workspace` skill. `gmail_helper.py` imports its `google_api.build_service`, which needs the `gmail.modify` and `gmail.send` scopes. To use another mail backend, replace `gmail_helper.py`. It reads one JSON request on stdin and prints one JSON result.

## Where things are stored

- Profile and progress: `~/.hermes/state/broker_optout/` (the profile is chmod 600 and never leaves your machine, except in the letters you send)
- Follow-up TODOs: `~/org/refile.org`, deduplicated by an `:OPTOUT_ID:` property
- Override for testing: `OPTOUT_STATE`, `OPTOUT_ORG`

## Disclaimer

This is not legal advice. Broker contact details change, so if a request bounces, fix the entry in `brokers.json` (PRs welcome).

MIT licensed.
