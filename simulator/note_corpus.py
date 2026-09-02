"""Investigation-note text: genuine free-text notes versus copy-paste templates."""

from __future__ import annotations

import random

TEMPLATES = [
    "Reviewed alert. No suspicious activity found. Closing.",
    "Checked and verified. False positive. Closed as per SOP.",
    "Alert reviewed, no action required.",
    "Validated with asset owner. Benign activity.",
    "Known activity. Closing ticket.",
]

OPENERS = [
    "Triaged {category} alert on {asset}",
    "Investigated {rule} firing for {asset}",
    "Reviewed {category} detection from {source} against {asset}",
    "Analyst picked up {category} alert ({rule})",
    "Looked into the {rule} hit on {asset} reported via {source}",
    "Follow-up on {category} activity involving {asset}",
    "Case opened for {asset} after {source} flagged {category}",
]
FINDINGS = [
    "process tree shows {proc} spawned by scheduled task, matches change record CHG-{n}",
    "source IP {ip} belongs to internal vulnerability scanner range",
    "user {user} confirmed the login from a new device during travel",
    "hash {h} matched vendor signature; endpoint isolated and reimaged",
    "traffic volume {kb} KB to {ip} consistent with backup window",
    "credential failures came from a misconfigured service account on {asset}",
    "correlated with firewall block, no successful connection observed",
    "EDR telemetry shows no persistence; memory scan clean",
    "confirmed with application team, deployment window matched timestamp",
    "packet capture reviewed, DNS queries resolve to CDN infrastructure",
    "login originated from the corporate VPN pool and MFA succeeded",
    "file was a signed vendor installer; hash present on the approved software list",
    "the outbound connection was the patch management agent contacting its relay {ip}",
    "asset owner {user} confirmed the maintenance window, no unauthorised change",
    "USB device matched an approved hardware ID, DLP shows no file transfer",
    "the scan came from the quarterly penetration test range agreed with {user}",
    "mail gateway quarantined the attachment before delivery, recipient did not open it",
    "account lockout caused by a stale cached credential on {asset}",
    "web requests were the uptime monitor hitting the health endpoint every {kb} seconds",
]
ACTIONS = [
    "Closed as false positive; tuning request raised for {rule}.",
    "Escalated to IR with evidence bundle attached.",
    "Remediated: account disabled, password reset, ticket {ticket}.",
    "No action required; documented for trend review.",
    "Marked benign after owner confirmation; monitoring rule left unchanged.",
    "Raised ticket {ticket} for patching; follow-up in 7 days.",
    "Added the source to the allow-list with a 30 day expiry and noted it in the runbook.",
    "Closed; recommended the detection be scoped to exclude the scanner subnet.",
    "Handed over to the platform team under {ticket} for a permanent fix.",
    "Closed as duplicate of an earlier case on the same asset.",
    "Verified with the user directly, no further action.",
]
DETAILS = [
    " Time spent: {mins} minutes.",
    " Reviewed {n} related events over the previous {days} days.",
    " Second analyst {user} peer-reviewed the conclusion.",
    " Similar pattern seen once earlier this quarter.",
    "",
    "",
]

PROCS = ["powershell.exe", "wscript.exe", "svchost.exe", "cmd.exe", "rundll32.exe", "python.exe"]
USERS = ["a.sharma", "r.iyer", "m.khan", "s.patel", "d.roy", "k.nair", "svc_backup", "svc_monitor"]


def _ip(rnd: random.Random) -> str:
    return f"10.{rnd.randint(0, 255)}.{rnd.randint(0, 255)}.{rnd.randint(1, 254)}"


def free_text_note(rnd: random.Random, *, category: str, asset: str, source: str, rule: str, ticket: str | None) -> str:
    opener = rnd.choice(OPENERS).format(category=category.replace("_", " "), asset=asset, source=source, rule=rule)
    finding = rnd.choice(FINDINGS).format(
        proc=rnd.choice(PROCS), n=rnd.randint(1000, 9999), ip=_ip(rnd), user=rnd.choice(USERS),
        h=f"{rnd.getrandbits(64):016x}", kb=rnd.randint(40, 9000), asset=asset,
    )
    action = rnd.choice(ACTIONS).format(rule=rule, ticket=ticket or f"REM-{rnd.randint(1000, 9999)}")
    detail = rnd.choice(DETAILS).format(mins=rnd.randint(5, 90), n=rnd.randint(2, 40), days=rnd.choice([7, 14, 30]), user=rnd.choice(USERS))
    return f"{opener}. {finding[0].upper()}{finding[1:]}. {action}{detail}"


def template_note(rnd: random.Random) -> str:
    return rnd.choice(TEMPLATES)
