"""Reports for people (decision D9): the pull-request summary comment (level 1) and the repo health page (level 2).
Both are pure functions of findings, the purity rows and, optionally, the previous run's findings."""
import html
from collections import Counter
from datetime import datetime, timezone

GATES = ("block", "warn", "report")


def _family(check):
    return check.rsplit("-", 1)[0].removeprefix("SL-")


def pr_summary(findings, checks, stage, failed, top=5):
    new = [f for f in findings if f.status == "new"]
    g = Counter(f.gate for f in new)
    lines = [f"### {'❌ Shift-left: fix before merge' if failed else '✅ Shift-left: no blocking problems'} ({stage})", "",
             f"**{g['block']}** blocking · **{g['warn']}** warnings · {g['report']} for the record · "
             f"{sum(f.status == 'baseline' for f in findings)} already known (baseline) · "
             f"{sum(f.status == 'suppressed' for f in findings)} allowed with a reason", ""]
    pick = [f for f in new if f.gate == "block"][:top] or [f for f in new if f.gate == "warn"][:top]
    if pick:
        lines += [f"**{'Blocking' if pick[0].gate == 'block' else 'Top warnings'}**", "", "| Where | Check | What |", "|---|---|---|"]
        for f in pick:
            where = f.file + (f":{f.line}" if f.line else "")
            lines.append(f"| `{where}` | {f.check} {checks[f.check]['title']} | {f.message.replace('|', '/')[:140]} |")
        lines.append("")
    lines.append("Full list on the changed lines (SARIF) and in the health page artifact.")
    return "\n".join(lines) + "\n"


CSS = """body{margin:0;background:#fff;color:#1f1f1f;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1060px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:30px 0 8px;
border-bottom:1.5px dashed #1f1f1f;padding-bottom:3px}.muted{color:#666}.tiles{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.tile{border:1.5px solid #1f1f1f;border-radius:12px;padding:10px 14px;min-width:120px}.tile b{display:block;font-size:24px}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13.5px}th,td{border:1px solid #bbb;padding:5px 7px;text-align:left;
vertical-align:top}th{background:#f4f4f1}code{font:12.5px ui-monospace,Menlo,monospace}.up{color:#a33}.down{color:#286}
.wrap{overflow-x:auto}.fail{background:#fdf0f0}.pass{background:#f0f8f3}"""


def _t(rows, head):
    e = html.escape
    return ('<div class="wrap"><table><tr>' + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" +
            "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table></div>")


def health_page(project_name, findings, checks, purity_rows, notes, missing, stage, failed, previous=None):
    e = html.escape
    new = [f for f in findings if f.status == "new"]
    g = Counter(f.gate for f in new)
    fam_now = Counter(_family(f.check) for f in new)
    fam_before = Counter(_family(x["check"]) for x in (previous or []) if x.get("status", "new") == "new")

    def trend(fam):
        if previous is None:
            return ""
        d = fam_now[fam] - fam_before[fam]
        return f'<span class="{"up" if d > 0 else "down"}">{"+" if d > 0 else ""}{d}</span>' if d else "same"

    fams = sorted(set(fam_now) | set(fam_before))
    by_fam = [(e(fm), *(str(sum(1 for f in new if _family(f.check) == fm and f.gate == gt)) for gt in GATES), trend(fm)) for fm in fams]
    pr = purity_rows or []
    pc = Counter(r["verdict"] for r in pr)
    could = [r for r in pr if r.get("could_be_pure")]
    untested = [r for r in pr if r["verdict"] == "pure" and not r.get("tested") and not r.get("notebook")]
    cplx = [f for f in new if f.check.startswith(("SL-CPLX", "SL-CLEAN-02")) and f.check != "SL-CPLX-04"]
    dead = [f for f in findings if f.check == "SL-CPLX-04" and f.status == "new"]
    missing_rows = [f for f in findings if f.check.startswith(("SL-SETUP", "SL-DEP-02")) and f.status == "new"]

    def loc(f):
        return f"<code>{e(f.file)}{':' + str(f.line) if f.line else ''}</code>"

    top = [f for f in new if f.gate in ("block", "warn")][:60]
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Repo Health: {e(project_name)}</title><style>{CSS}</style></head><body><main>",
             f"<h1>Repo health: {e(project_name)}</h1><p class='muted'>Shift-left checks, stage <b>{e(stage)}</b>, "
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
             f"{'Trend compared with the previous run.' if previous is not None else 'No previous run to compare with.'}</p>",
             f"<div class='tiles'><div class='tile {'fail' if failed else 'pass'}'><b>{'FAIL' if failed else 'PASS'}</b>merge gate</div>"
             f"<div class='tile'><b>{g['block']}</b>blocking</div><div class='tile'><b>{g['warn']}</b>warnings</div>"
             f"<div class='tile'><b>{g['report']}</b>for the record</div>"
             f"<div class='tile'><b>{pc['pure']}/{len(pr)}</b>functions pure</div><div class='tile'><b>{len(untested)}</b>pure, untested</div></div>"]
    if missing:
        parts.append(f"<p class='muted'>Tools not installed, so their checks did not run: {e(', '.join(missing))}.</p>")
    parts.append("<h2>Findings by area</h2>" + _t(by_fam, ["Family", "Blocking", "Warnings", "Reported", "Change"]))
    parts.append(f"<h2>Purity</h2><p>{len(pr)} functions: {pc['pure']} pure, {pc['impure']} impure, {pc['unknown']} unknown "
                 f"(unknown is never counted as pure).</p>")
    if could:
        parts.append("<p><b>Impure, but could be pure</b>: move the read, write or clock to the caller, then unit test the logic.</p>" +
                     _t([(f"<code>{e(r['module'])}:{r['line']}</code>", e(r["function"]), e(r["hint"])) for r in could], ["Where", "Function", "How"]))
    if untested:
        parts.append("<p><b>Pure but untested</b>: the cheapest tests to add.</p>" +
                     _t([(f"<code>{e(r['module'])}:{r['line']}</code>", e(r["function"])) for r in untested], ["Where", "Function"]))
    if cplx:
        parts.append("<h2>Complexity hot spots</h2>" + _t([(loc(f), e(checks[f.check]["title"]), e(f.message)) for f in cplx], ["Where", "Check", "What"]))
    if dead:
        parts.append("<h2>Possibly dead code</h2><p class='muted'>Confirm before deleting: jobs may call these from config.</p>" +
                     _t([(loc(f), e(f.message)) for f in dead], ["Where", "What"]))
    if missing_rows:
        parts.append("<h2>What the repo is missing</h2>" + _t([(loc(f), e(checks[f.check]["title"]), e(f.message)) for f in missing_rows], ["Where", "Check", "What"]))
    parts.append("<h2>Blocking and warnings</h2>" + _t(
        [(e(f.gate), loc(f), f"{e(f.check)} {e(checks[f.check]['title'])}", e(f.message[:200]), e(f"{f.tool} {f.tool_rule}")) for f in top],
        ["Gate", "Where", "Check", "What", "Found by"]) + (f"<p class='muted'>Showing 60 of {g['block'] + g['warn']}.</p>" if g['block'] + g['warn'] > 60 else ""))
    if notes:
        parts.append("<h2>Notes</h2><ul>" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>")
    parts.append("</main></body></html>")
    return "\n".join(parts)
