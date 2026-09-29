"""Publish generated portfolio markdown as a GitHub Gist."""

from __future__ import annotations

from github import Auth, Github, InputFileContent
from github.GithubException import GithubException


def publish_gist(
    github_token: str,
    markdown: str,
    *,
    filename: str = "gitfolio.md",
    description: str = "GitFolio portfolio",
    public: bool = True,
) -> str:
    """Create a Gist and return its public HTML URL."""
    if not github_token:
        raise ValueError("GitHub PAT가 필요합니다. gist 권한을 포함해야 합니다.")
    if not markdown.strip():
        raise ValueError("업로드할 포트폴리오가 없습니다.")

    github = Github(auth=Auth.Token(github_token))
    try:
        gist = github.get_user().create_gist(
            public,
            {filename: InputFileContent(markdown)},
            description,
        )
    except GithubException as exc:
        status = exc.status
        if status == 401:
            raise RuntimeError("GitHub 인증에 실패했습니다. PAT를 확인하세요.") from exc
        if status == 403:
            raise RuntimeError(
                "Gist 생성 권한이 없습니다. PAT에 gist 스코프를 추가하세요."
            ) from exc
        raise RuntimeError(f"Gist 생성에 실패했습니다. (GitHub {status})") from exc

    url = gist.html_url
    if not url:
        raise RuntimeError("Gist는 생성됐지만 URL을 받지 못했습니다.")
    return url
