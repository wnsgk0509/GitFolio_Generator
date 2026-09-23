# GitFolio Generator — Agent Instructions

## Project Overview

GitFolio Generator is a local Streamlit app that turns a GitHub repository's
Commit / PR diff history into a Korean markdown portfolio.

Flow:

1. User provides a GitHub repository URL and a GitHub username.
2. The app fetches commit and pull-request diffs for that contributor.
3. Gemini analyzes the extracted logs and writes a markdown portfolio with
   five sections: 프로젝트 소개, 역할, 핵심 기능, 트러블슈팅, 느낀점.
4. The user previews and downloads the generated markdown.

Target runtime: Python 3.10+, local only (no production server).

## Stack

- UI: Streamlit (`app.py`)
- GitHub API: PyGithub
- LLM: `google-genai` (Gemini)
- Config: `python-dotenv` + Streamlit sidebar / secrets (never hardcode keys)

## Architecture

Keep I/O, GitHub access, and LLM generation in separate modules.

```
GitFolio_Generator/
├── app.py                 # Streamlit UI and orchestration only
├── github_extractor.py    # Fetch commits / PRs / diffs (to be added)
├── llm_generator.py       # Gemini prompt + markdown generation (to be added)
├── requirements.txt
├── .env                   # local secrets (gitignored)
├── agents.md
└── .gitignore
```

Responsibilities:

| Module | Does | Does not |
| --- | --- | --- |
| `app.py` | Collect inputs, load keys, call modules, render markdown | Call GitHub REST or Gemini SDK directly |
| `github_extractor.py` | Authenticate with PAT, parse repo URL, collect commit/PR diffs for the given username | Call Gemini, render UI |
| `llm_generator.py` | Build prompts, call Gemini, return markdown string | Fetch GitHub data, render Streamlit widgets |

Suggested data contract (implement in later modules):

```python
# github_extractor.py
def extract_activity(
    repo_url: str,
    username: str,
    github_token: str,
) -> dict:
    """Return structured commit/PR summaries + diffs for `username`."""

# llm_generator.py
def generate_portfolio(
    activity: dict,
    gemini_api_key: str,
    model: str = "gemini-2.0-flash",
) -> str:
    """Return markdown covering the five required sections."""
```

`activity` should be JSON-serializable (dicts/lists/strings). Prefer summarized
diffs over raw unbounded patches so prompts stay within token limits.

## Secrets

Never hardcode `GITHUB_TOKEN`, `GEMINI_API_KEY`, or personal access tokens.

Resolution order:

1. Streamlit sidebar input for the current session (password fields)
2. `st.secrets` (`.streamlit/secrets.toml`) if present
3. Environment variables loaded via `python-dotenv` from `.env`

Example `.env` keys:

```
GITHUB_TOKEN=
GEMINI_API_KEY=
```

Do not commit `.env` or `.streamlit/secrets.toml`.

## Portfolio Markdown Contract

Generated markdown must include these five H2 sections, in this order:

1. `## 프로젝트 소개`
2. `## 역할`
3. `## 핵심 기능`
4. `## 트러블슈팅`
5. `## 느낀점`

Content must be grounded in extracted GitHub activity. If evidence is missing,
state that explicitly instead of inventing commits, features, or metrics.

Language: Korean unless the user later asks otherwise.

## Coding Rules

- Python 3.10+ typing (`str | None`, `list[str]`, etc.). No `Optional` unless needed for compatibility.
- Functions over classes unless state is required (e.g. a GitHub client wrapper).
- Public functions: type hints + a short docstring.
- Fail fast with clear, user-facing Korean error messages (invalid URL, 401, empty activity, Gemini quota).
- Do not swallow exceptions silently. Catch API errors at the UI boundary in `app.py`.
- Keep Streamlit session state keys prefixed (`gf_`) to avoid collisions.
- Do not log tokens, PATs, or full raw diffs to disk.
- Cap extracted diff size (truncate large files; skip binaries).
- No extra dependencies unless they are added to `requirements.txt`.
- Match existing style: 4-space indent, UTF-8, no unused imports.

## UI Rules (`app.py`)

- Page title: GitFolio Generator.
- Required inputs: repository URL, GitHub username, GitHub PAT, Gemini API key.
- Primary action: a single button that runs extract → generate.
- Show progress (extracting vs generating).
- Preview markdown with `st.markdown` and offer download as `.md`.
- Do not auto-run generation on every rerun.

## What Not To Do

- Do not put GitHub or Gemini SDK calls inside Streamlit widget callbacks beyond orchestrating the two modules.
- Do not invent a database, auth system, or multi-user backend.
- Do not generate HTML portfolios; markdown only unless requested later.
- Do not expand scope into extra modules until the user asks.
