"""Gemini Flash portfolio generation."""

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
- 트러블 슈팅은 diff와 커밋 메시지에서 드러난 문제-해결 흐름을 중심으로 쓰세요.
- 본인 역할은 해당 username의 커밋/PR에서 관찰된 기여에 한정하세요.
""".strip()


def generate_portfolio(
    activity: dict,
    gemini_api_key: str,
    model: str = DEFAULT_MODEL,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Call Gemini Flash and return markdown with the five required H2 sections.

    Retries transient 503/429 errors and falls back to other Flash models
    when a model is overloaded or missing.
    """
    if not gemini_api_key:
        raise ValueError("Gemini API Key가 필요합니다.")

    client = genai.Client(api_key=gemini_api_key)
    prompt = _build_user_prompt(activity)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.3,
    )

    last_error: Exception | None = None
    for model_name in _model_chain(model):
        for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
            _notify(
                on_progress,
                f"`{model_name}` 호출 중... ({attempt}/{MAX_ATTEMPTS_PER_MODEL})",
            )
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
                        f"서버가 혼잡합니다(503). {wait:.0f}초 후 재시도합니다.",
                    )
                    time.sleep(wait)
                    continue
                if _is_retryable(exc):
                    _notify(on_progress, f"`{model_name}` 혼잡이 길어 다른 Flash 모델로 전환합니다.")
                    break
                raise RuntimeError(f"Gemini API 호출에 실패했습니다: {exc}") from exc

            text = (response.text or "").strip()
            if text:
                if model_name != model:
                    _notify(on_progress, f"대체 모델 `{model_name}` 으로 생성했습니다.")
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
