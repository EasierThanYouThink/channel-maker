"""A local-only, stdlib-only dashboard for the Channel Maker Engine.

Read views come straight from repository files via the existing engine modules.
Every write action goes through `actions.py`'s fixed whitelist, which always
shells out to an existing `tools/*.py` CLI (never re-implements its logic) and
never builds a shell string — only explicit argv lists. Binds to 127.0.0.1 only:
this is a local developer tool, not a service exposed to the network.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dashboard.actions import ActionError, run_action  # noqa: E402
from tools.dashboard.markdown import render as render_markdown  # noqa: E402
from tools.dashboard.views import (  # noqa: E402
    channel_detail,
    channel_overview,
    list_channels,
    review_queue,
    wiki_pages,
)

PAGE_SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
:root {{
  --bg: #0f1115; --panel: #171b22; --card: #1e242e; --line: #2c3440;
  --text: #e8ecf1; --muted: #9aa4b2; --accent: #6ea8fe; --good: #3fb950; --warn: #d29922; --bad: #f85149;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: var(--bg); color: var(--text); }}
.topbar {{ background: var(--panel); border-bottom: 1px solid var(--line); padding: 0.7rem 1.5rem; display: flex; gap: 1.2rem; align-items: center; position: sticky; top: 0; }}
.topbar .brand {{ font-weight: 700; letter-spacing: 0.02em; }}
.topbar nav a {{ margin-right: 1rem; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
main {{ max-width: 1080px; margin: 0 auto; padding: 1.5rem; }}
.hero {{ background: linear-gradient(135deg, #1c2b4a, #171b22); border: 1px solid var(--line); border-radius: 12px; padding: 1.2rem 1.4rem; margin-bottom: 1rem; }}
.hero h2 {{ margin: 0 0 0.4rem; font-size: 1.5rem; }}
.hero .sub {{ color: var(--muted); font-size: 0.9rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; margin-bottom: 1rem; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem; }}
.card h3 {{ margin: 0 0 0.6rem; font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
.card .big {{ font-size: 1.05rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
td, th {{ border-bottom: 1px solid var(--line); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }}
th {{ color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
pre {{ background: #0d1015; border: 1px solid var(--line); border-radius: 8px; padding: 0.6rem; overflow-x: auto; font-size: 0.82rem; }}
.badge {{ display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; background: #2c3440; font-size: 0.82em; margin: 0.1rem 0.15rem 0.1rem 0; white-space: nowrap; }}
.badge.state {{ background: #1c2b4a; border: 1px solid var(--accent); }}
.badge.good {{ background: rgba(63,185,80,0.18); border: 1px solid var(--good); }}
.badge.warn {{ background: rgba(210,153,34,0.16); border: 1px solid var(--warn); }}
.badge.bad {{ background: rgba(248,81,73,0.15); border: 1px solid var(--bad); }}
.badge.now {{ background: var(--accent); color: #0b1020; font-weight: 700; }}
.badge.done {{ background: rgba(63,185,80,0.15); color: #9ee6a8; }}
.badge.todo {{ opacity: 0.55; }}
.stepper {{ display: flex; flex-wrap: wrap; gap: 0.25rem; margin: 0.4rem 0; }}
.dot {{ display: inline-block; width: 0.55rem; height: 0.55rem; border-radius: 50%; margin-right: 0.35rem; vertical-align: baseline; }}
.dot.ok {{ background: var(--good); }} .dot.miss {{ background: var(--bad); }} .dot.idle {{ background: var(--muted); }}
.progress {{ height: 8px; background: #2c3440; border-radius: 999px; overflow: hidden; margin: 0.5rem 0; }}
.progress > div {{ height: 100%; background: linear-gradient(90deg, var(--accent), #a371f7); }}
.kv {{ display: grid; grid-template-columns: auto 1fr; gap: 0.2rem 0.8rem; font-size: 0.9rem; }}
.kv dt {{ color: var(--muted); }} .kv dd {{ margin: 0; }}
footer {{ color: var(--muted); font-size: 0.8rem; padding: 1rem 1.5rem 2rem; text-align: center; }}
@media (max-width: 640px) {{ main {{ padding: 1rem; }} }}
</style></head>
<body>
<div class="topbar"><span class="brand">🎬 Channel Maker</span><nav><a href="/">Channels</a><a href="/review">Review queue</a></nav></div>
<main>
<h1 style="font-size:1.2rem;color:var(--muted);font-weight:600;">{title}</h1>
{body}
</main>
<footer>Local only · 127.0.0.1 · reads files, gated actions shell out to the same CLIs</footer>
</body></html>
"""


def _page(title: str, body: str) -> bytes:
    return PAGE_SHELL.format(title=html.escape(title), body=body).encode("utf-8")


def _channels_page() -> bytes:
    rows = []
    for channel in list_channels(ROOT):
        if "error" in channel:
            rows.append(f"<tr><td>{html.escape(channel['channel_id'])}</td><td colspan='4'><span class='badge bad'>ERROR</span> {html.escape(channel['error'])}</td></tr>")
            continue
        status_cls = "good" if channel["status"] == "COMPLETE" else ("warn" if channel["waiting_for"] else "")
        rows.append(
            f"<tr><td><a href='/overview/{html.escape(channel['channel_id'])}'><b>{html.escape(channel['channel_id'])}</b></a> "
            f"<a href='/channel/{html.escape(channel['channel_id'])}' style='color:var(--muted);font-size:0.8em;'>raw</a></td>"
            f"<td><span class='badge state'>{html.escape(channel['state'])}</span></td>"
            f"<td><span class='badge {status_cls}'>{html.escape(channel['status'])}</span></td>"
            f"<td>{html.escape(channel['waiting_for'] or '—')}</td><td>{html.escape(channel['next_action'])}</td></tr>"
        )
    table = "<div class='card'><h3>Channels — click a name for its control panel</h3><table><tr><th>Channel</th><th>State</th><th>Status</th><th>Waiting for</th><th>Next action</th></tr>" + "".join(rows) + "</table></div>"
    return _page("Channels", table)


def _overview_page(channel_id: str) -> bytes:
    overview = channel_overview(ROOT, channel_id)
    header, progress = overview["header"], overview["progress"]
    completed = set(progress["completed"])
    chips = []
    for state in progress["states"]:
        if state == progress["current"]:
            cls = "now"
        elif state in completed:
            cls = "done"
        else:
            cls = "todo"
        chips.append(f"<span class='badge {cls}'>{html.escape(state)}</span>")
    strip = "<div class='stepper'>" + "".join(chips) + "</div>"
    pct = round(100 * (progress["position"] or 0) / max(progress["total"], 1))
    bar = f"<div class='progress'><div style='width:{pct}%'></div></div>"
    counts = " ".join(
        f"<span class='badge {'warn' if v else ''}'>{html.escape(k)}: {v}</span>"
        for k, v in overview["review_counts"].items()
    )
    pilots = "".join(
        f"<tr><td>{html.escape(p['pilot_id'])}</td><td>{html.escape(str(p['decision']))}</td>"
        f"<td>{'<span class=\'badge good\'>frozen</span>' if p['frozen'] else '<span class=\'badge todo\'>open</span>'}</td></tr>"
        for p in overview["pilots"]
    ) or "<tr><td colspan='3' style='color:var(--muted)'>No pilots yet — Stage 9 will create the first.</td></tr>"
    episodes = "".join(
        f"<tr><td>{html.escape(e['episode_id'])}</td><td>{html.escape(str(e['decision']))}</td></tr>"
        for e in overview["episodes"]
    ) or "<tr><td colspan='2' style='color:var(--muted)'>No episodes yet — they start after CHANNEL_READY.</td></tr>"
    services = "".join(
        f"<tr><td>{html.escape(name)}</td>"
        f"<td><span class='dot {'ok' if info.get('available') else 'miss'}'></span>{'OK' if info.get('available') else 'MISS'}</td>"
        f"<td style='color:var(--muted)'>{html.escape(str(info.get('detail')))}</td></tr>"
        for name, info in overview["services"].items()
    )
    style = " ".join(
        f"<span class='badge {'good' if ok else 'todo'}'>{html.escape(name)}: {'✓' if ok else '…'}</span>"
        for name, ok in overview["style_pages"].items()
    )
    vault = overview.get("vault", {})
    vault_pages = "".join(
        f"<div style='margin:0.45rem 0;padding:0.5rem 0.6rem;background:#0d1015;border:1px solid var(--line);border-radius:8px;'>"
        f"<b>{html.escape(p['title'])}</b><br>"
        f"<span style='color:var(--muted);font-size:0.82em;'><code>{html.escape(p['path'])}</code></span><br>"
        f"<span style='font-size:0.88em;'>{html.escape(p['excerpt'])}</span></div>"
        for p in vault.get("recent_pages", [])
    ) or "<p style='color:var(--muted)'>No wiki notes yet — Stage 1.6 seeds the style snapshot.</p>"
    vault_card = f"""
      <div class="card" style="grid-column: 1 / -1;"><h3>🔮 Obsidian vault — the channel's learning memory</h3>
      <p><code>{html.escape(vault.get('vault_path', ''))}</code>
      <a href="{html.escape(vault.get('obsidian_url', '#'))}"
         style="display:inline-block;margin-left:0.6rem;padding:0.35rem 0.9rem;background:#7c3aed;color:#fff;border-radius:999px;font-weight:600;">Open in Obsidian ⧉</a></p>
      <p>{style}</p>
      <h4 style="color:var(--muted);font-size:0.82rem;text-transform:uppercase;letter-spacing:0.05em;">Latest notes</h4>
      {vault_pages}
      <p><a href="/wiki/{html.escape(channel_id)}">Browse full wiki →</a></p></div>
    """
    ops = overview["next_allowed_action"]
    ops_badges = " ".join(f"<span class='badge'>{html.escape(op)}</span>" for op in ops.get("allowed_operations", []))
    gate = "<span class='badge bad'>human gate — decision ref required</span>" if ops.get("requires_human_decision") else ""
    ref_warnings = "".join(
        f"<p><span class='badge warn'>recoverable</span> {html.escape(warning)}</p>"
        for warning in overview.get("reference_warnings", [])
    )
    events = "".join(
        f"<tr><td>{e['sequence']}</td><td>{html.escape(e['operation'])}</td><td>{html.escape(e['from_state'])} -&gt; {html.escape(e['to_state'])}</td>"
        f"<td>{html.escape(e['actor'])}</td><td>{html.escape(e['reason'])}</td></tr>"
        for e in overview["recent_events"]
    )
    body = f"""
    <div class="hero">
      <h2>🎬 {html.escape(header['name'])}</h2>
      <div class="sub">{html.escape(channel_id)} · {html.escape(str(header.get('niche')))} · {html.escape(str(header.get('archetype')))} · renderer {html.escape(str(header.get('renderer')))} · v{html.escape(str(header.get('version')))}</div>
      <p><span class="badge state">{html.escape(header['state'])}</span> <span class="badge">{html.escape(header['status'])}</span>
      <span class="badge">step {progress['position']}/{progress['total']} · {pct}%</span></p>
      {bar}
      {strip}
    </div>
    <div class="grid">
      <div class="card"><h3>▶ Next action</h3>
        <p class="big">{html.escape(overview['next_action_text'] or '—')}</p>
        <p>{ops_badges} {gate}</p>
        {ref_warnings}
        <details><summary style="color:var(--muted);cursor:pointer;">machine detail</summary>
        <pre>{html.escape(json.dumps(ops, indent=2))}</pre></details>
      </div>
      <div class="card"><h3>👀 Review queue — this channel</h3><p>{counts}</p>
        <p><a href="/review">Global queue →</a></p>
      </div>
    </div>
    {vault_card}
    <div class="grid">
      <div class="card"><h3>🧪 Pilots</h3><table><tr><th>Pilot</th><th>Decision</th><th>Frozen</th></tr>{pilots}</table></div>
      <div class="card"><h3>🎞 Episodes</h3><table><tr><th>Episode</th><th>Decision</th></tr>{episodes}</table></div>
      <div class="card"><h3>🔌 Services</h3><table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>{services}</table></div>
    </div>
    <div class="card"><h3>📜 Recent events</h3>
    <table><tr><th>#</th><th>Op</th><th>Transition</th><th>Actor</th><th>Reason</th></tr>{events}</table></div>
    """
    return _page(f"Control panel: {channel_id}", body)


def _channel_page(channel_id: str) -> bytes:
    detail = channel_detail(ROOT, channel_id)
    identity, state, next_action = detail["identity"], detail["state"], detail["next_allowed_action"]
    events_rows = "".join(
        f"<tr><td>{e['sequence']}</td><td>{html.escape(e['operation'])}</td><td>{html.escape(e['from_state'])} -&gt; {html.escape(e['to_state'])}</td>"
        f"<td>{html.escape(e['actor'])}</td><td>{html.escape(e['reason'])}</td></tr>"
        for e in detail["recent_events"]
    )
    body = f"""
    <h2>{html.escape(identity['name'])} ({html.escape(channel_id)})</h2>
    <p><span class="badge">{html.escape(state['state'])}</span> <span class="badge">{html.escape(state['status'])}</span></p>
    <p><b>Waiting for:</b> {html.escape(state['waiting_for'] or 'nothing')}</p>
    <p><b>Next action:</b> {html.escape(state['next_action'])}</p>
    <h3>Allowed operations</h3>
    <pre>{html.escape(json.dumps(next_action, indent=2))}</pre>
    <h3>Recent events</h3>
    <table><tr><th>#</th><th>Op</th><th>Transition</th><th>Actor</th><th>Reason</th></tr>{events_rows}</table>
    <p><a href="/wiki/{html.escape(channel_id)}">Browse this channel's wiki</a></p>
    <p><a href="/overview/{html.escape(channel_id)}">Open control-panel overview</a></p>
    """
    return _page(f"Channel: {channel_id}", body)


def _wiki_page(channel_id: str) -> bytes:
    pages = wiki_pages(ROOT, channel_id)
    sections = "".join(
        f"<h3>{html.escape(page['title'])} <span class='badge'>{html.escape(page['kind'])}</span> <span class='badge'>{html.escape(page['authority'])}</span></h3>"
        f"<p><code>{html.escape(page['path'])}</code></p>{render_markdown(page['body'])}"
        for page in pages
    )
    return _page(f"Wiki: {channel_id}", sections or "<p>No wiki pages yet.</p>")


def _review_page() -> bytes:
    queue = review_queue(ROOT)
    sections = []
    for category, items in queue.items():
        rows = "".join(f"<tr><td>{html.escape(item.get('channel_id', ''))}</td><td><pre>{html.escape(json.dumps(item, indent=2))}</pre></td></tr>" for item in items)
        sections.append(f"<h3>{html.escape(category)} ({len(items)})</h3><table><tr><th>Channel</th><th>Record</th></tr>{rows}</table>")
    return _page("Review queue", "".join(sections))


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            if not parts:
                self._send(200, _channels_page())
            elif parts[0] == "channel" and len(parts) == 2:
                self._send(200, _channel_page(parts[1]))
            elif parts[0] == "overview" and len(parts) == 2:
                self._send(200, _overview_page(parts[1]))
            elif parts[0] == "wiki" and len(parts) == 2:
                self._send(200, _wiki_page(parts[1]))
            elif parts[0] == "review":
                self._send(200, _review_page())
            else:
                self._send(404, _page("Not found", "<p>Not found.</p>"))
        except Exception as exc:  # noqa: BLE001 - surfaced to the local user, not a remote caller
            self._send(500, _page("Error", f"<pre>{html.escape(str(exc))}</pre>"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/action":
            self._send(404, b"{}", "application/json")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
            result = run_action(
                request["action"], request.get("params", {}), confirmed=bool(request.get("confirmed", False)),
            )
            payload = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            self._send(200, json.dumps(payload).encode("utf-8"), "application/json")
        except ActionError as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json")
        except Exception as exc:  # noqa: BLE001
            self._send(500, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8420)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Channel Maker dashboard: http://127.0.0.1:{args.port}/  (local only, Ctrl+C to stop)")
    with suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
