"""Gemini Flash portfolio generation with Hybrid (Standard & Map-Reduce) modes."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable

from google import genai
from google.genai import types

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODELS = (
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
)
MAX_ATTEMPTS_PER_MODEL = 3
RETRY_BASE_SECONDS = 2.0
MAP_REDUCE_CHUNK_SIZE = 40

PORTFOLIO_HEADINGS = (
    "프로젝트 소개",
    "본인 역할",
    "핵심 기능",
    "트러블 슈팅 및 해결",
    "배운 점 및 회고",
)

SYSTEM_INSTRUCTION = """
당신은 GitHub README, 커밋 메시지, PR, diff 로그만을 근거로 개발자 포트폴리오를 작성하는 기술 문서 작성자입니다.

[출력 형식 — 위반 금지]
- 반드시 마크다운만 출력하세요. 서문, 맺음말, 코드펜스(```)로 전체 문서를 감싸지 마세요.
- 최상위 헤딩은 `##` 만 사용하고, 아래 다섯 개를 이 순서 그대로 빠짐없이 포함하세요.
- 이 다섯 개 외에 다른 `##` 헤딩을 추가하지 마세요.
- 하위 내용은 `###` 또는 불릿을 써도 됩니다.

## 프로젝트 소개
## 본인 역할
## 핵심 기능
## 트러블 슈팅 및 해결
## 배운 점 및 회고

[내용 규칙]
- 언어는 한국어입니다.
- 제공된 데이터에 없는 기능, 수치, 성과를 지어내지 마세요.
- 근거가 부족한 항목은 추측 대신 "커밋/PR 데이터에서 확인하기 어렵다"고 명시하세요.
- 트러블 슈팅은 diff와 커밋 메시지에서 드러난 문제-해결 흐름(문제 원인, 수정된 코드 로직)을 중심으로 쓰세요.
- 본인 역할은 해당 username의 커밋/PR에서 관찰된 기여에 한정하세요.
""".strip()

CHUNK_SUMMARY_INSTRUCTION = """
당신은 GitHub 커밋과 PR diff 내역을 정밀 분석하는 시니어 기술 분석가입니다.
제공된 활동 데이터 청크(커밋/PR 목록)를 분석하여 다음 세 가지 관점에서 핵심 내용을 한국어 불릿 포인트로 상세히 추출하세요.

1. [구현 기능 및 변경 사항]: 어떤 모듈/기능이 추가되거나 개선되었는가 (주요 파일/함수/로직)
2. [트러블슈팅 및 버그 해결 흐름]: 코드 diff에서 드러난 문제점, 원인, 수정된 해결 로직
3. [기술 스택 및 아키텍처 패턴]: 사용된 프레임워크, 라이브러리, 구조적 패턴

[작성 규칙]
- 절대 없는 사실을 지어내지 마세요.
- 커밋 메시지와 diff에 명시된 파일명, 주요 메서드/설정 키워드를 구체적으로 인용하세요.
""".strip()


def _generate_with_retry(
    client: genai.Client,
    prompt: str,
    system_instruction: str,
    preferred_model: str,
    temperature: float = 0.3,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Generate content with automatic retry on 429/503 and fallback to other models."""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
    )

    last_error: Exception | None = None
    for model_name in _model_chain(preferred_model):
        for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
            except Exception as exc:
                last_error = exc
                if _is_model_unavailable(exc):
                    _notify(on_progress, f"`{model_name}` 을(를) 사용할 수 없어 다음 모델로 전환합니다.")
                    break
                if _is_retryable(exc) and attempt < MAX_ATTEMPTS_PER_MODEL:
                    wait = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                    _notify(
                        on_progress,
                        f"서버가 혼잡합니다(503/429). {wait:.0f}초 후 재시도합니다.",
                    )
                    time.sleep(wait)
                    continue
                if _is_retryable(exc):
                    _notify(on_progress, f"`{model_name}` 혼잡이 길어 다른 Flash 모델로 전환합니다.")
                    break
                raise RuntimeError(f"Gemini API 호출에 실패했습니다: {exc}") from exc

            text = (response.text or "").strip()
            if text:
                return text
            last_error = RuntimeError("Gemini가 빈 응답을 반환했습니다.")
            if attempt < MAX_ATTEMPTS_PER_MODEL:
                time.sleep(RETRY_BASE_SECONDS)
                continue
            break

    raise RuntimeError(
        "Gemini 서버가 혼잡하거나 모델을 사용할 수 없습니다. "
        "잠시 후 다시 눌러 주세요. "
        f"(마지막 오류: {last_error})"
    ) from last_error


def generate_portfolio(
    activity: dict,
    gemini_api_key: str,
    model: str = DEFAULT_MODEL,
    mode: str = "standard",
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Generate portfolio markdown supporting 'standard' (single-shot) and 'deep' (Map-Reduce) modes."""
    if not gemini_api_key:
        raise ValueError("Gemini API Key가 필요합니다.")

    client = genai.Client(api_key=gemini_api_key)
    commits = activity.get("commits", [])

    # If deep mode is requested and commits exceed CHUNK_SIZE, use Map-Reduce
    if mode == "deep" and len(commits) > MAP_REDUCE_CHUNK_SIZE:
        return _generate_portfolio_map_reduce(
            client=client,
            activity=activity,
            preferred_model=model,
            on_progress=on_progress,
        )

    # Standard fast mode (single-shot)
    _notify(on_progress, f"Gemini 모델(`{model}`) 호출 중...")
    prompt = _build_user_prompt(activity)
    return _generate_with_retry(
        client=client,
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        preferred_model=model,
        on_progress=on_progress,
    )


def _generate_portfolio_map_reduce(
    client: genai.Client,
    activity: dict,
    preferred_model: str,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Divide commits into chunks, summarize each chunk, and synthesize into the final 5-section portfolio."""
    commits = activity.get("commits", [])
    pull_requests = activity.get("pull_requests", [])
    readme = activity.get("readme", "")
    repo_name = activity.get("repo_full_name", "")
    username = activity.get("username", "")

    # 1. Chunking commits
    chunk_size = MAP_REDUCE_CHUNK_SIZE
    chunks = [commits[i : i + chunk_size] for i in range(0, len(commits), chunk_size)]
    total_chunks = len(chunks)
    _notify(on_progress, f"정밀 모드(Map-Reduce): 커밋 {len(commits)}개를 {total_chunks}개 청크로 분할 요약합니다.")

    chunk_summaries: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        _notify(on_progress, f"청크 요약 분석 중... ({idx}/{total_chunks})")
        chunk_payload = {
            "chunk_index": idx,
            "total_chunks": total_chunks,
            "repo": repo_name,
            "username": username,
            "commits": chunk,
        }
        chunk_prompt = (
            f"다음은 {repo_name} 저장소의 {username} 활동 데이터 청크 ({idx}/{total_chunks})입니다.\n"
            "핵심 구현 기능, 트러블슈팅/버그 해결 흐름, 기술 스택을 한국어로 요약하세요:\n\n"
            f"{json.dumps(chunk_payload, ensure_ascii=False, indent=2)}"
        )
        summary = _generate_with_retry(
            client=client,
            prompt=chunk_prompt,
            system_instruction=CHUNK_SUMMARY_INSTRUCTION,
            preferred_model=preferred_model,
            on_progress=on_progress,
        )
        chunk_summaries.append(f"### [활동 청크 {idx}/{total_chunks} 분석 요약]\n{summary}")

    # 2. Final synthesis (Reduce)
    _notify(on_progress, "청크 요약들을 병합하여 최종 5대 섹션 포트폴리오를 종합 작성하는 중입니다...")
    combined_summaries = "\n\n".join(chunk_summaries)

    pr_summary_text = ""
    if pull_requests:
        pr_items = []
        for pr in pull_requests:
            pr_items.append(
                f"- PR #{pr.get('number')}: {pr.get('title')} (상태: {pr.get('state')}, 머지됨: {pr.get('merged')})\n"
                f"  설명: {pr.get('body', '')[:200]}"
            )
        pr_summary_text = "\n[Pull Request 목록]\n" + "\n".join(pr_items)

    synthesis_prompt = (
        "다음은 GitHub 저장소의 전체 활동 내역을 시간순으로 분할 분석한 요약본들입니다.\n"
        "이 분석 요약들과 README를 종합하여 완성도 높은 개발자 기술 포트폴리오를 작성하세요.\n\n"
        f"[저장소 정보]\n- 저장소: {repo_name}\n- 기여자: {username}\n\n"
        f"[저장소 README]\n{readme}\n\n"
        f"{pr_summary_text}\n\n"
        f"[활동 내역 청크별 정밀 분석 요약]\n{combined_summaries}\n\n"
        "반드시 최상위 헤딩 `##` 5개를 순서대로 빠짐없이 작성하세요:\n"
        "## 프로젝트 소개\n"
        "## 본인 역할\n"
        "## 핵심 기능\n"
        "## 트러블 슈팅 및 해결\n"
        "## 배운 점 및 회고\n"
    )

    return _generate_with_retry(
        client=client,
        prompt=synthesis_prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        preferred_model=preferred_model,
        on_progress=on_progress,
    )


def _model_chain(preferred: str) -> list[str]:
    ordered: list[str] = []
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    for name in (preferred, env_model, *FALLBACK_MODELS):
        cleaned = (name or "").strip()
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered


def _is_retryable(exc: BaseException) -> bool:
    code = _error_code(exc)
    if code in {429, 500, 502, 503, 504}:
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "unavailable",
            "high demand",
            "resource_exhausted",
            "overloaded",
            "try again later",
            "503",
            "429",
        )
    )


def _is_model_unavailable(exc: BaseException) -> bool:
    code = _error_code(exc)
    if code in {404, 400}:
        text = str(exc).lower()
        return any(
            token in text
            for token in ("not found", "not_found", "unknown model", "invalid model")
        )
    text = str(exc).lower()
    return "not found" in text or "not_found" in text


def _error_code(exc: BaseException) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _notify(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)


def _build_user_prompt(activity: dict) -> str:
    required = "\n".join(f"## {title}" for title in PORTFOLIO_HEADINGS)
    payload = json.dumps(activity, ensure_ascii=False, indent=2)
    return (
        "다음 GitHub 활동 데이터를 분석해 포트폴리오 마크다운을 작성하세요.\n"
        "출력에는 아래 헤딩이 반드시 포함되어야 합니다:\n"
        f"{required}\n\n"
        "[GitHub 활동 데이터]\n"
        f"{payload}\n"
    )
