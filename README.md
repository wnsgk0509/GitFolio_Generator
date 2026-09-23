# GitFolio Generator

GitHub 저장소의 커밋·PR diff를 읽어, Gemini로 한국어 마크다운 포트폴리오를 만드는 로컬 Streamlit 앱입니다.

분석 결과는 아래 다섯 섹션으로 고정됩니다.

- 프로젝트 소개
- 본인 역할
- 핵심 기능
- 트러블 슈팅 및 해결
- 배운 점 및 회고

## 요구 사항

- Python 3.10 이상
- GitHub Personal Access Token (PAT)
- Gemini API Key

## 설치

```bash
git clone https://github.com/wnsgk0509/GitFolio_Generator.git
cd GitFolio_Generator

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
# source venv/bin/activate

pip install -r requirements.txt
```

## 환경 변수

API 키는 코드에 넣지 마세요. 사이드바에 직접 입력하거나 `.env`를 사용합니다.

프로젝트 루트에 `.env` 파일을 만들고 다음을 채웁니다.

```env
GITHUB_TOKEN=ghp_your_token
GEMINI_API_KEY=your_gemini_key
# optional
# GEMINI_MODEL=gemini-2.5-flash
```

| 키 | 설명 |
| --- | --- |
| `GITHUB_TOKEN` | 대상 저장소를 읽을 수 있는 GitHub PAT |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey)에서 발급한 키 |
| `GEMINI_MODEL` | (선택) 기본 Gemini 모델. 미설정 시 `gemini-3.6-flash` |

`.env`와 `.streamlit/secrets.toml`은 `.gitignore`에 포함되어 있습니다.

## 실행

```bash
streamlit run app.py
```

1. 사이드바에 GitHub PAT와 Gemini API Key를 입력합니다. (`.env`가 있으면 자동으로 채워집니다.)
2. 저장소 URL과 분석할 GitHub Username을 입력합니다.
3. **포트폴리오 생성**을 누릅니다.
4. 미리보기를 확인한 뒤 마크다운 파일로 다운로드합니다.

## 동작 방식

```
app.py  →  GitHub 추출  →  Gemini 분석  →  마크다운 미리보기/다운로드
             (src/github_extractor.py)   (src/llm_generator.py)
```

1. PyGithub로 README, 해당 유저의 최근 커밋, PR과 diff를 가져옵니다.
2. 토큰 한도를 넘지 않도록 커밋·PR은 각각 최근 50개, patch는 항목당 상위 50줄만 사용합니다.
3. Gemini Flash가 다섯 개 `##` 헤딩이 있는 포트폴리오를 작성합니다.
4. 특정 모델이 503(혼잡)이면 잠시 재시도하고, 안 되면 다른 Flash 모델로 넘어갑니다.

## 프로젝트 구조

```
GitFolio_Generator/
├── app.py                  # Streamlit UI
├── src/
│   ├── github_extractor.py # README / 커밋 / PR 추출
│   └── llm_generator.py    # Gemini 포트폴리오 생성
├── requirements.txt
├── agents.md               # 코딩 지시서
└── .gitignore
```

## 주의

- 비공개 저장소는 PAT에 `repo` 권한이 필요합니다.
- Username은 GitHub 로그인 이름과 같아야 해당 기여자의 커밋·PR이 잡힙니다.
- Gemini 서버가 혼잡하면 생성에 1~2분이 걸릴 수 있습니다. 실패하면 잠시 후 다시 시도하세요.
