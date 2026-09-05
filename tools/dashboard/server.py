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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dashboard.actions import ActionError, run_action  # noqa: E402
from tools.dashboard.markdown import render as render_markdown  # noqa: E402
from tools.dashboard.views import channel_detail, list_channels, review_queue, wiki_pages  # noqa: E402


PAGE_SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 960px; }}
a {{ color: #0b5fff; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }}
pre {{ background: #f4f4f4; padding: 0.6rem; overflow-x: auto; }}
.badge {{ display: inline-block; padding: 0.1rem 0.5rem; border-radius: 0.5rem; background: #eee; font-size: 0.85em; }}
nav a {{ margin-right: 1rem; }}
</style></head>
<body>
<nav><a href="/">Channels</a><a href="/review">Review queue</a></nav>
<h1>{title}</h1>
{body}
</body></html>
"""


def _page(title: str, body: str) -> bytes:
    return PAGE_SHELL.format(title=html.escape(title), body=body).encode("utf-8")


def _channels_page() -> bytes:
    rows = []
    for channel in list_channels(ROOT):
        if "error" in channel:
            rows.append(f"<tr><td>{html.escape(channel['channel_id'])}</td><td colspan='4'>ERROR: {html.escape(channel['error'])}</td></tr>")
            continue
        rows.append(
            f"<tr><td><a href='/channel/{html.escape(channel['channel_id'])}'>{html.escape(channel['channel_id'])}</a></td>"
            f"<td>{html.escape(channel['state'])}</td><td>{html.escape(channel['status'])}</td>"
            f"<td>{html.escape(channel['waiting_for'] or '')}</td><td>{html.escape(channel['next_action'])}</td></tr>"
        )
    table = "<table><tr><th>Channel</th><th>State</th><th>Status</th><th>Waiting for</th><th>Next action</th></tr>" + "".join(rows) + "</table>"
    return _page("Channels", table)


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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            if not parts:
                self._send(200, _channels_page())
            elif parts[0] == "channel" and len(parts) == 2:
                self._send(200, _channel_page(parts[1]))
            elif parts[0] == "wiki" and len(parts) == 2:
                self._send(200, _wiki_page(parts[1]))
            elif parts[0] == "review":
                self._send(200, _review_page())
            else:
                self._send(404, _page("Not found", "<p>Not found.</p>"))
        except Exception as exc:  # noqa: BLE001 - surfaced to the local user, not a remote caller
            self._send(500, _page("Error", f"<pre>{html.escape(str(exc))}</pre>"))

    def do_POST(self) -> None:  # noqa: N802
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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
