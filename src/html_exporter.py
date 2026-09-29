"""Export generated portfolio markdown to self-contained styled HTML."""

from __future__ import annotations

import markdown


def export_portfolio_html(
    markdown_text: str,
    title: str = "GitFolio 포트폴리오",
) -> str:
    """Convert markdown into a styled, standalone HTML document for viewing or PDF printing."""
    body_html = markdown.markdown(
        markdown_text,
        extensions=[
            "fenced_code",
            "tables",
            "nl2br",
            "sane_lists",
        ],
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --primary: #2563eb;
      --text: #1e293b;
      --bg: #ffffff;
      --muted: #64748b;
      --border: #e2e8f0;
      --code-bg: #f8fafc;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.65;
      color: var(--text);
      background-color: #f1f5f9;
      margin: 0;
      padding: 40px 20px;
    }}

    .container {{
      max-width: 860px;
      margin: 0 auto;
      background: var(--bg);
      padding: 48px;
      border-radius: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
    }}

    h1, h2, h3, h4 {{
      color: #0f172a;
      font-weight: 700;
      line-height: 1.3;
      margin-top: 1.6em;
      margin-bottom: 0.6em;
    }}

    h1 {{
      font-size: 2rem;
      border-bottom: 2px solid var(--border);
      padding-bottom: 0.4em;
      margin-top: 0;
    }}

    h2 {{
      font-size: 1.45rem;
      border-bottom: 1.5px solid var(--border);
      padding-bottom: 0.3em;
      color: var(--primary);
    }}

    h3 {{
      font-size: 1.2rem;
    }}

    p {{
      margin: 0.8em 0;
    }}

    ul, ol {{
      padding-left: 24px;
      margin: 0.8em 0;
    }}

    li {{
      margin: 0.35em 0;
    }}

    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.88em;
      background-color: var(--code-bg);
      padding: 0.2em 0.4em;
      border-radius: 4px;
      border: 1px solid var(--border);
    }}

    pre {{
      background-color: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
      margin: 1em 0;
    }}

    pre code {{
      background-color: transparent;
      padding: 0;
      border: none;
      font-size: 0.9em;
    }}

    blockquote {{
      margin: 1.2em 0;
      padding: 12px 20px;
      background-color: #f8fafc;
      border-left: 4px solid var(--primary);
      color: var(--muted);
      border-radius: 0 8px 8px 0;
    }}

    hr {{
      border: none;
      border-top: 1px solid var(--border);
      margin: 2em 0;
    }}

    a {{
      color: var(--primary);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}

    @media print {{
      body {{
        background: #ffffff;
        padding: 0;
      }}
      .container {{
        box-shadow: none;
        padding: 0;
        max-width: 100%;
      }}
      h2, h3, pre, blockquote {{
        break-inside: avoid;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    {body_html}
  </div>
</body>
</html>
"""
