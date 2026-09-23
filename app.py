"""GitFolio Generator — Streamlit entrypoint.

Orchestrates GitHub activity extraction and Gemini portfolio generation.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from src.github_extractor import (
    get_readme,
    get_repo,
    get_user_commits,
    get_user_pull_requests,
)
from src.llm_generator import generate_portfolio

load_dotenv()

PAGE_TITLE = "GitFolio Generator"
PORTFOLIO_SECTIONS = (
    "프로젝트 소개",
    "본인 역할",
    "핵심 기능",
    "트러블 슈팅 및 해결",
    "배운 점 및 회고",
)


def _secret(name: str) -> str:
    """Resolve a secret from Streamlit secrets, then environment variables."""
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, "")


def init_session_state() -> None:
    if "gf_portfolio_md" not in st.session_state:
        st.session_state.gf_portfolio_md = ""
    if "gf_error" not in st.session_state:
        st.session_state.gf_error = ""


def render_sidebar() -> tuple[str, str]:
    st.sidebar.header("API Keys")
    st.sidebar.caption("키는 세션에만 사용합니다. 코드에 하드코딩하지 마세요.")

    github_token = st.sidebar.text_input(
        "GitHub PAT",
        value=_secret("GITHUB_TOKEN"),
        type="password",
        help="repo 범위가 있는 Personal Access Token",
        key="gf_github_token",
    )
    gemini_api_key = st.sidebar.text_input(
        "Gemini API Key",
        value=_secret("GEMINI_API_KEY"),
        type="password",
        key="gf_gemini_api_key",
    )
    return github_token.strip(), gemini_api_key.strip()


def generate_portfolio_markdown(
    repo_url: str,
    username: str,
    github_token: str,
    gemini_api_key: str,
) -> str:
    """Extract GitHub activity, then generate portfolio markdown with Gemini."""
    with st.status("포트폴리오 생성 중...", expanded=True) as status:
        status.update(label="데이터 추출 중...", state="running")
        st.write("저장소 README · 커밋 · PR diff를 가져오는 중입니다.")
        with st.spinner("GitHub 데이터를 추출하는 중..."):
            repo = get_repo(repo_url, github_token)
            activity = {
                "repo_url": repo_url,
                "repo_full_name": repo.full_name,
                "username": username,
                "readme": get_readme(repo),
                "commits": get_user_commits(repo, username),
                "pull_requests": get_user_pull_requests(repo, username),
            }

        commit_count = len(activity["commits"])
        pr_count = len(activity["pull_requests"])
        st.write(f"추출 완료: 커밋 {commit_count}개, PR {pr_count}개")

        if commit_count == 0 and pr_count == 0:
            raise RuntimeError(
                f"'{username}'의 커밋/PR을 찾지 못했습니다. Username과 저장소를 확인하세요."
            )

        status.update(label="AI 분석 중...", state="running")
        st.write("Gemini Flash가 포트폴리오 마크다운을 작성하는 중입니다.")
        with st.spinner("AI가 포트폴리오를 분석·작성하는 중..."):
            markdown = generate_portfolio(
                activity,
                gemini_api_key,
                on_progress=st.write,
            )

        status.update(label="생성 완료", state="complete")
        st.write("포트폴리오 초안이 준비되었습니다.")

    return markdown


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon="🗂️", layout="wide")
    init_session_state()

    st.title(PAGE_TITLE)
    st.write(
        "GitHub 커밋·PR diff를 바탕으로 마크다운 포트폴리오를 생성합니다. "
        f"구성: **{' · '.join(PORTFOLIO_SECTIONS)}**"
    )

    github_token, gemini_api_key = render_sidebar()

    with st.form("gf_generate_form"):
        repo_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/owner/repo",
            key="gf_repo_url",
        )
        username = st.text_input(
            "GitHub Username",
            placeholder="contributor-login",
            key="gf_username",
        )
        submitted = st.form_submit_button("포트폴리오 생성", type="primary")

    if submitted:
        st.session_state.gf_error = ""
        st.session_state.gf_portfolio_md = ""

        missing = []
        if not repo_url.strip():
            missing.append("Repository URL")
        if not username.strip():
            missing.append("Username")
        if not github_token:
            missing.append("GitHub PAT")
        if not gemini_api_key:
            missing.append("Gemini API Key")

        if missing:
            st.session_state.gf_error = f"필수 입력 누락: {', '.join(missing)}"
        else:
            try:
                st.session_state.gf_portfolio_md = generate_portfolio_markdown(
                    repo_url=repo_url.strip(),
                    username=username.strip(),
                    github_token=github_token,
                    gemini_api_key=gemini_api_key,
                )
            except Exception as exc:
                st.session_state.gf_error = str(exc)

    if st.session_state.gf_error:
        st.error(st.session_state.gf_error)

    if st.session_state.gf_portfolio_md:
        st.subheader("미리보기")
        st.markdown(st.session_state.gf_portfolio_md)
        st.download_button(
            label="마크다운 다운로드",
            data=st.session_state.gf_portfolio_md,
            file_name="gitfolio.md",
            mime="text/markdown",
        )


if __name__ == "__main__":
    main()
