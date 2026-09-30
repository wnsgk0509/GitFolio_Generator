"""GitHub activity extraction via PyGithub."""

from __future__ import annotations

from urllib.parse import urlparse

from github import Auth, Github
from github.GithubException import GithubException
from github.Repository import Repository

from collections.abc import Callable

DEFAULT_MAX_COMMITS = 80
DEFAULT_MAX_PULL_REQUESTS = 50
DEEP_MAX_COMMITS = 200
DEEP_MAX_PULL_REQUESTS = 80
MAX_PATCH_LINES = 50
MAX_README_CHARS = 12_000


def _is_meaningful_commit(message: str, files: list) -> bool:
    """Filter out empty commits or automated merges without actual code modifications."""
    if not files:
        return False
    clean = message.strip()
    if clean.startswith(("Merge branch ", "Merge pull request #", "Merge remote-tracking branch ")):
        total_changes = sum(
            getattr(f, "additions", 0) + getattr(f, "deletions", 0) for f in files
        )
        if total_changes == 0:
            return False
    total_diff = sum(getattr(f, "additions", 0) + getattr(f, "deletions", 0) for f in files)
    if total_diff == 0:
        return False
    return True


def parse_repo_full_name(repo_url: str) -> str:
    """Return `owner/repo` from a GitHub URL or SSH remote."""
    raw = repo_url.strip()
    if not raw:
        raise ValueError("GitHub 저장소 URL이 비어 있습니다.")

    if raw.startswith("git@github.com:"):
        path = raw.split(":", 1)[1]
    else:
        parsed = urlparse(raw)
        path = parsed.path if parsed.scheme else raw

    path = path.strip().strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("유효한 GitHub 저장소 URL이 아닙니다. 예: https://github.com/owner/repo")
    return f"{parts[0]}/{parts[1]}"


def get_repo(repo_url: str, github_token: str) -> Repository:
    """Authenticate with a PAT and return the target repository."""
    if not github_token:
        raise ValueError("GitHub PAT가 필요합니다.")

    github = Github(auth=Auth.Token(github_token))
    full_name = parse_repo_full_name(repo_url)
    try:
        return github.get_repo(full_name)
    except GithubException as exc:
        _raise_github_error(exc)


def get_readme(repo: Repository) -> str:
    """Return README text, or an empty string if the repository has none."""
    try:
        content_file = repo.get_readme()
    except GithubException as exc:
        if exc.status == 404:
            return ""
        _raise_github_error(exc)

    try:
        text = content_file.decoded_content.decode("utf-8")
    except UnicodeDecodeError:
        text = content_file.decoded_content.decode("utf-8", errors="replace")

    if len(text) > MAX_README_CHARS:
        return text[:MAX_README_CHARS] + "\n\n... (README truncated)"
    return text


def get_user_commits(
    repo: Repository,
    username: str,
    max_commits: int = DEFAULT_MAX_COMMITS,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Return up to `max_commits` recent meaningful commits by `username` with truncated patches."""
    if not username.strip():
        raise ValueError("GitHub Username이 필요합니다.")

    try:
        commit_pages = repo.get_commits(author=username.strip())
    except GithubException as exc:
        _raise_github_error(exc)

    results: list[dict] = []
    scanned_count = 0
    try:
        for commit in commit_pages:
            if len(results) >= max_commits:
                break
            scanned_count += 1

            files = list(commit.files or [])
            msg = (commit.commit.message if commit.commit else "") or ""
            if not _is_meaningful_commit(msg, files):
                continue

            patch_chunks: list[str] = []
            file_summaries: list[dict] = []
            for changed in files:
                file_summaries.append(
                    {
                        "filename": changed.filename,
                        "status": changed.status,
                        "additions": changed.additions,
                        "deletions": changed.deletions,
                    }
                )
                patch_chunks.append(f"--- {changed.filename} ({changed.status})")
                if changed.patch:
                    patch_chunks.append(changed.patch)

            author_date = ""
            if commit.commit and commit.commit.author and commit.commit.author.date:
                author_date = commit.commit.author.date.isoformat()

            results.append(
                {
                    "sha": commit.sha,
                    "message": msg,
                    "date": author_date,
                    "html_url": commit.html_url,
                    "files": file_summaries,
                    "patch": _truncate_patch("\n".join(patch_chunks)),
                }
            )

            if on_progress and len(results) % 10 == 0:
                on_progress(f"커밋 diff 수집 중... ({len(results)}/{max_commits})")
    except GithubException as exc:
        _raise_github_error(exc)

    if on_progress:
        on_progress(f"커밋 수집 완료: 유의미한 커밋 {len(results)}개 (총 {scanned_count}개 탐색)")

    return results


def get_user_pull_requests(
    repo: Repository,
    username: str,
    max_prs: int = DEFAULT_MAX_PULL_REQUESTS,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Return up to `max_prs` recent PRs authored by `username` with truncated patches."""
    login = username.strip().lower()
    if not login:
        raise ValueError("GitHub Username이 필요합니다.")

    results: list[dict] = []
    try:
        pulls = repo.get_pulls(state="all", sort="updated", direction="desc")
        for pull in pulls:
            if len(results) >= max_prs:
                break
            if not pull.user or pull.user.login.lower() != login:
                continue

            patch_chunks: list[str] = []
            file_summaries: list[dict] = []
            for changed in pull.get_files():
                file_summaries.append(
                    {
                        "filename": changed.filename,
                        "status": changed.status,
                        "additions": changed.additions,
                        "deletions": changed.deletions,
                    }
                )
                patch_chunks.append(f"--- {changed.filename} ({changed.status})")
                if changed.patch:
                    patch_chunks.append(changed.patch)

            results.append(
                {
                    "number": pull.number,
                    "title": pull.title,
                    "body": pull.body or "",
                    "state": pull.state,
                    "merged": bool(pull.merged),
                    "html_url": pull.html_url,
                    "files": file_summaries,
                    "patch": _truncate_patch("\n".join(patch_chunks)),
                }
            )

            if on_progress and len(results) % 5 == 0:
                on_progress(f"PR diff 수집 중... ({len(results)}/{max_prs})")
    except GithubException as exc:
        _raise_github_error(exc)

    if on_progress and results:
        on_progress(f"PR 수집 완료: 총 {len(results)}개")

    return results


def _truncate_patch(patch: str) -> str:
    if not patch.strip():
        return ""
    lines = patch.splitlines()
    if len(lines) <= MAX_PATCH_LINES:
        return "\n".join(lines)
    kept = "\n".join(lines[:MAX_PATCH_LINES])
    omitted = len(lines) - MAX_PATCH_LINES
    return f"{kept}\n... ({omitted} lines truncated)"


def _raise_github_error(exc: GithubException) -> None:
    status = exc.status
    if status == 401:
        raise RuntimeError("GitHub 인증에 실패했습니다. PAT를 확인하세요.") from exc
    if status == 404:
        raise RuntimeError("저장소를 찾을 수 없습니다. URL과 PAT 권한을 확인하세요.") from exc
    if status == 403:
        raise RuntimeError(
            "GitHub API 요청이 거부되었습니다. Rate limit 또는 저장소 권한을 확인하세요."
        ) from exc
    raise RuntimeError(f"GitHub API 오류 ({status}).") from exc
