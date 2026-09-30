"""GitFolio Generator — Streamlit entrypoint.

Orchestrates GitHub activity extraction and Gemini portfolio generation.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from src.gist_exporter import publish_gist
from src.github_extractor import (
    DEEP_MAX_COMMITS,
    DEEP_MAX_PULL_REQUESTS,
    DEFAULT_MAX_COMMITS,
    DEFAULT_MAX_PULL_REQUESTS,
    get_readme,
    get_repo,
    get_user_commits,
    get_user_pull_requests,
)
from src.html_exporter import export_portfolio_html
from src.llm_generator import generate_portfolio
from src.notion_exporter import send_markdown_to_notion

load_dotenv()

PAGE_TITLE = "GitFolio Generator"
PORTFOLIO_SECTIONS = (
    "프로젝트 소개",
    "본인 역할",
    "핵심 기능",
    "트러블 슈팅 및 해결",
    "배운 점 및 회고",
)


def _secret(*names: str) -> str:
    """Resolve a secret from Streamlit secrets, then environment variables, checking aliases."""
    for name in names:
        try:
            value = st.secrets.get(name, "")
            if value:
                return str(value)
        except Exception:
            pass
        val = os.getenv(name, "")
        if val:
            return val
    return ""


def init_session_state() -> None:
    if "gf_portfolio_md" not in st.session_state:
        st.session_state.gf_portfolio_md = ""
    if "gf_error" not in st.session_state:
        st.session_state.gf_error = ""
    if "gf_repo_url_saved" not in st.session_state:
        st.session_state.gf_repo_url_saved = ""
    if "gf_username_saved" not in st.session_state:
        st.session_state.gf_username_saved = ""
    if "gf_gist_url" not in st.session_state:
        st.session_state.gf_gist_url = ""
    if "gf_notion_url" not in st.session_state:
        st.session_state.gf_notion_url = ""


def render_sidebar() -> tuple[str, str, str, str]:
    st.sidebar.header("API Keys")
    st.sidebar.caption("키는 세션에만 사용합니다. 코드에 하드코딩하지 마세요.")

    github_token = st.sidebar.text_input(
        "GitHub PAT",
        value=_secret("GITHUB_TOKEN", "GITHUB_PAT"),
        type="password",
        help="repo, gist 범위가 있는 Personal Access Token",
        key="gf_github_token",
    )
    gemini_api_key = st.sidebar.text_input(
        "Gemini API Key",
        value=_secret("GEMINI_API_KEY"),
        type="password",
        key="gf_gemini_api_key",
    )

    with st.sidebar.expander("Notion 설정 (선택)", expanded=False):
        notion_token = st.text_input(
            "Notion Token",
            value=_secret("NOTION_TOKEN"),
            type="password",
            help="Notion Internal Integration Token (secret_...)",
            key="gf_sidebar_notion_token",
        )
        notion_target = st.text_input(
            "Notion Target (Page/DB)",
            value=_secret("NOTION_TARGET", "NOTION_TARGET_ID"),
            help="기본으로 내보낼 Notion 페이지 또는 데이터베이스 URL/ID",
            key="gf_sidebar_notion_target",
        )

    return (
        github_token.strip(),
        gemini_api_key.strip(),
        notion_token.strip(),
        notion_target.strip(),
    )


def generate_portfolio_markdown(
    repo_url: str,
    username: str,
    github_token: str,
    gemini_api_key: str,
    mode: str = "standard",
) -> str:
    """Extract GitHub activity, then generate portfolio markdown with Gemini."""
    is_deep = mode == "deep"
    max_commits = DEEP_MAX_COMMITS if is_deep else DEFAULT_MAX_COMMITS
    max_prs = DEEP_MAX_PULL_REQUESTS if is_deep else DEFAULT_MAX_PULL_REQUESTS
    mode_label = "정밀 분할 모드 (Map-Reduce)" if is_deep else "표준 고속 모드"

    with st.status(f"포트폴리오 생성 중... ({mode_label})", expanded=True) as status:
        status.update(label="데이터 추출 및 노이즈 필터링 중...", state="running")
        st.write(f"저장소 README · 커밋(최대 {max_commits}개) · PR diff를 가져오는 중입니다.")
        with st.spinner("GitHub 데이터를 추출하고 노이즈를 필터링하는 중..."):
            repo = get_repo(repo_url, github_token)
            activity = {
                "repo_url": repo_url,
                "repo_full_name": repo.full_name,
                "username": username,
                "readme": get_readme(repo),
                "commits": get_user_commits(
                    repo, username, max_commits=max_commits, on_progress=st.write
                ),
                "pull_requests": get_user_pull_requests(
                    repo, username, max_prs=max_prs, on_progress=st.write
                ),
            }

        commit_count = len(activity["commits"])
        pr_count = len(activity["pull_requests"])
        st.write(f"추출 완료: 유의미한 커밋 {commit_count}개, PR {pr_count}개")

        if commit_count == 0 and pr_count == 0:
            raise RuntimeError(
                f"'{username}'의 유효한 커밋/PR을 찾지 못했습니다. Username과 저장소를 확인하세요."
            )

        status.update(label=f"AI 분석 중... ({mode_label})", state="running")
        st.write("Gemini Flash가 활동 내역을 심층 분석하고 포트폴리오를 작성하는 중입니다.")
        with st.spinner("AI가 포트폴리오를 분석·작성하는 중..."):
            markdown = generate_portfolio(
                activity,
                gemini_api_key,
                mode=mode,
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

    github_token, gemini_api_key, notion_token, notion_target = render_sidebar()

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
        analysis_mode = st.radio(
            "분석 모드",
            options=["standard", "deep"],
            format_func=lambda x: (
                "⚡ 표준 고속 모드 (추천: 최근 80개 커밋 및 노이즈 자동 제거, ~15초)"
                if x == "standard"
                else "🔍 정밀 분할 모드 (Map-Reduce: 최대 200개 커밋 전 기간 분석, ~40초)"
            ),
            index=0,
            horizontal=True,
            help="프로젝트 초기 아키텍처부터 전체 변경 내역을 망라하려면 정밀 분할 모드를 선택하세요.",
        )
        submitted = st.form_submit_button("포트폴리오 생성", type="primary")

    if submitted:
        st.session_state.gf_error = ""
        st.session_state.gf_portfolio_md = ""
        st.session_state.gf_gist_url = ""
        st.session_state.gf_notion_url = ""
        st.session_state.gf_repo_url_saved = repo_url.strip()
        st.session_state.gf_username_saved = username.strip()

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
                    mode=analysis_mode,
                )
            except Exception as exc:
                st.session_state.gf_error = str(exc)

    if st.session_state.gf_error:
        st.error(st.session_state.gf_error)

    if st.session_state.gf_portfolio_md:
        st.subheader("미리보기")
        st.markdown(st.session_state.gf_portfolio_md)

        st.divider()
        st.subheader("📤 포트폴리오 저장 및 공유")

        saved_repo = st.session_state.gf_repo_url_saved
        repo_slug = (
            saved_repo.rstrip("/").split("/")[-1].removesuffix(".git")
            if saved_repo
            else "project"
        )
        saved_user = st.session_state.gf_username_saved or "developer"

        html_content = export_portfolio_html(
            st.session_state.gf_portfolio_md,
            title=f"{repo_slug} 포트폴리오 ({saved_user})",
        )

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 마크다운 (.md) 다운로드",
                data=st.session_state.gf_portfolio_md,
                file_name=f"{repo_slug}_portfolio.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                label="📄 웹 / PDF 인쇄용 HTML 다운로드",
                data=html_content,
                file_name=f"{repo_slug}_portfolio.html",
                mime="text/html",
                help="브라우저에서 다운로드한 HTML을 열고 Ctrl+P(인쇄)를 누르면 PDF로 바로 저장할 수 있습니다.",
                use_container_width=True,
            )

        with st.expander("📋 마크다운 원본 텍스트 보기 (우측 상단 복사 아이콘 사용)"):
            st.code(st.session_state.gf_portfolio_md, language="markdown")

        st.write("")
        tab_gist, tab_notion = st.tabs(["🐙 GitHub Gist 배포", "📝 Notion으로 내보내기"])

        with tab_gist:
            st.caption(
                "GitHub Gist로 발행하여 외부에 바로 공유 가능한 공개/비공개 링크를 생성합니다. (PAT에 `gist` 스코프 필요)"
            )
            c_g1, c_g2 = st.columns([3, 1])
            with c_g1:
                gist_desc = st.text_input(
                    "Gist 설명",
                    value=f"GitFolio Portfolio - {repo_slug} ({saved_user})",
                    key="gf_gist_desc_input",
                )
            with c_g2:
                gist_public = st.checkbox("공개(Public) Gist", value=True, key="gf_gist_public_input")

            if st.button("🚀 Gist로 발행하기", type="secondary", key="gf_btn_gist"):
                if not github_token:
                    st.error("GitHub PAT가 필요합니다. 사이드바에 PAT를 입력해 주세요.")
                else:
                    try:
                        with st.spinner("Gist 생성 중..."):
                            gist_url = publish_gist(
                                github_token=github_token,
                                markdown=st.session_state.gf_portfolio_md,
                                filename=f"{repo_slug}_portfolio.md",
                                description=gist_desc,
                                public=gist_public,
                            )
                            st.session_state.gf_gist_url = gist_url
                    except Exception as exc:
                        st.error(f"Gist 생성 실패: {exc}")

            if st.session_state.gf_gist_url:
                st.success("Gist가 성공적으로 발행되었습니다!")
                st.link_button("🔗 생성된 Gist 열기", st.session_state.gf_gist_url)

        with tab_notion:
            st.caption(
                "Notion 페이지 또는 데이터베이스에 포트폴리오를 블록으로 추가합니다. "
                "(대상 페이지 우측 상단 `···` -> `연결(Connections)`에서 노션 Integration을 추가해야 합니다.)"
            )
            notion_token_input = st.text_input(
                "Notion Integration Token",
                value=notion_token,
                type="password",
                placeholder="secret_...",
                key="gf_notion_token_input",
            )
            c_n1, c_n2 = st.columns([2, 1])
            with c_n1:
                notion_target_input = st.text_input(
                    "Notion 대상 페이지 / 데이터베이스 URL 또는 ID",
                    value=notion_target,
                    placeholder="https://www.notion.so/...",
                    key="gf_notion_target_input",
                )
            with c_n2:
                notion_title_input = st.text_input(
                    "페이지 제목 (데이터베이스 저장 시 사용)",
                    value=f"{repo_slug} 포트폴리오 ({saved_user})",
                    key="gf_notion_title_input",
                )

            if st.button("🚀 Notion으로 전송하기", type="secondary", key="gf_btn_notion"):
                if not notion_token_input.strip():
                    st.error("Notion Integration Token을 입력해 주세요.")
                elif not notion_target_input.strip():
                    st.error("Notion 대상 페이지 또는 데이터베이스 URL/ID를 입력해 주세요.")
                else:
                    try:
                        with st.spinner("Notion 블록 변환 및 전송 중..."):
                            notion_page_url = send_markdown_to_notion(
                                notion_token=notion_token_input.strip(),
                                target=notion_target_input.strip(),
                                markdown=st.session_state.gf_portfolio_md,
                                page_title=notion_title_input.strip(),
                            )
                            st.session_state.gf_notion_url = notion_page_url
                    except Exception as exc:
                        st.error(f"Notion 전송 실패: {exc}")

            if st.session_state.gf_notion_url:
                st.success("Notion으로 성공적으로 전송되었습니다!")
                st.link_button("🔗 Notion 페이지 열기", st.session_state.gf_notion_url)


if __name__ == "__main__":
    main()
