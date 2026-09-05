"""A tiny, dependency-free Markdown-to-HTML renderer: headings, lists, code fences, paragraphs only."""

from __future__ import annotations

import html
import re


def render(body: str) -> str:
    lines = body.splitlines()
    html_parts: list[str] = []
    in_code = False
    in_list = False
    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                html_parts.append("</pre>")
            else:
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                html_parts.append("<pre>")
            in_code = not in_code
            continue
        if in_code:
            html_parts.append(html.escape(line))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            level = len(heading.group(1))
            html_parts.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
            continue
        item = re.match(r"^[-*]\s+(.*)$", line)
        if item:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{html.escape(item.group(1))}</li>")
            continue
        if in_list:
            html_parts.append("</ul>")
            in_list = False
        if line.strip():
            html_parts.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        html_parts.append("</ul>")
    if in_code:
        html_parts.append("</pre>")
    return "\n".join(html_parts)
