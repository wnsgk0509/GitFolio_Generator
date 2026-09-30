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
GITHUB_TOKEN=ghp_your_token # 또는 GITHUB_PAT
GEMINI_API_KEY=your_gemini_key
# optional
# GEMINI_MODEL=gemini-3.6-flash
# NOTION_TOKEN=secret_your_notion_integration_token
# NOTION_TARGET=https://www.notion.so/your_page_or_database_id
```

| 키 | 설명 |
| --- | --- |
| `GITHUB_TOKEN` / `GITHUB_PAT` | 대상 저장소 접근 및 Gist 생성을 위한 GitHub PAT (`repo`, `gist` 권한) |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey)에서 발급한 키 |
| `GEMINI_MODEL` | (선택) 기본 Gemini 모델. 미설정 시 `gemini-3.6-flash` |
| `NOTION_TOKEN` | (선택) Notion Internal Integration Secret Token |
| `NOTION_TARGET` | (선택) 포트폴리오를 내보낼 기본 Notion 페이지 또는 데이터베이스 URL/ID |

`.env`와 `.streamlit/secrets.toml`은 `.gitignore`에 포함되어 있습니다.

## 실행

```bash
streamlit run app.py
```

1. 사이드바에 GitHub PAT와 Gemini API Key를 입력합니다. (`.env`가 있으면 자동으로 채워집니다.)
2. 저장소 URL과 분석할 GitHub Username을 입력합니다.
3. **분석 모드**를 선택합니다:
   - **⚡ 표준 고속 모드 (기본값)**: 노이즈 커밋(빈 커밋, 단순 머지)을 자동 필터링하고 최대 80개의 유의미한 커밋을 선별하여 단일 호출로 빠르게 생성 (~15초).
   - **🔍 정밀 분할 모드 (Map-Reduce)**: 커밋 수가 많거나 초기 아키텍처부터 전체를 분석해야 할 때, 최대 200개 커밋을 40개 단위 청크로 분할 요약한 뒤 최종 종합 (~40초).
4. **포트폴리오 생성**을 누릅니다.
5. 미리보기를 확인한 뒤 원하는 형태로 저장 및 공유합니다:
   - **마크다운 (.md) 다운로드**: 기본 마크다운 파일로 저장
   - **웹 / PDF 인쇄용 HTML 다운로드**: 깔끔한 스타일이 적용된 단일 HTML 파일로 다운로드 (브라우저에서 열어 `Ctrl + P`로 고품질 PDF 저장 가능)
   - **클립보드 복사**: 원본 마크다운 코드 블록 우측 상단 아이콘으로 원클릭 복사
   - **GitHub Gist 배포**: 외부에 즉시 공유 가능한 Gist 링크 생성
   - **Notion으로 내보내기**: 내 Notion 페이지 또는 데이터베이스에 네이티브 블록 형태로 자동 전송

## 동작 방식

```
app.py  →  GitHub 추출 & 필터링  →  Gemini 분석 (단일 or Map-Reduce)  →  미리보기 및 다중 내보내기
             (src/github_extractor.py)       (src/llm_generator.py)              (Markdown / HTML / Gist / Notion)
```

1. PyGithub로 README, 해당 유저의 커밋, PR과 diff를 가져오며, 단순 머지나 변경사항 없는 노이즈 커밋을 필터링합니다.
2. 분석 모드에 따라:
   - **표준 모드**: 최근 80개 커밋을 Gemini Flash의 대용량 컨텍스트로 한 번에 전달하여 고속 분석.
   - **정밀 모드**: 40개 단위 청크로 나누어 핵심 기능/트러블슈팅을 1차 요약(Map)한 뒤, 최종 5개 섹션 포트폴리오로 종합(Reduce).
3. Gemini Flash가 다섯 개 `##` 헤딩이 있는 포트폴리오를 작성합니다.
4. 특정 모델이 503(혼잡)이면 잠시 재시도하고, 안 되면 다른 Flash 모델로 넘어갑니다.
5. 생성된 포트폴리오는 로컬 파일(.md, .html) 또는 클라우드(Gist, Notion)로 즉시 내보낼 수 있습니다.

## 프로젝트 구조

```
GitFolio_Generator/
├── app.py                  # Streamlit UI 및 오케스트레이션
├── src/
│   ├── github_extractor.py # README / 커밋 / PR 추출
│   ├── llm_generator.py    # Gemini 포트폴리오 생성
│   ├── html_exporter.py    # 웹/PDF 인쇄용 독립형 HTML 렌더러
│   ├── gist_exporter.py    # GitHub Gist 자동 배포
│   └── notion_exporter.py  # Notion 블록 변환 및 API 전송
├── requirements.txt
├── agents.md               # 코딩 지시서
└── .gitignore
```

## 주의

- 비공개 저장소는 PAT에 `repo` 권한이 필요합니다.
- GitHub Gist로 내보내기를 사용하려면 PAT에 `gist` 권한이 필요합니다.
- Notion으로 내보내려면 Notion 개발자 센터에서 Integration을 생성하고 대상 페이지에 Connection으로 연결해야 합니다.
- Username은 GitHub 로그인 이름과 같아야 해당 기여자의 커밋·PR이 잡힙니다.
- Gemini 서버가 혼잡하면 생성에 1~2분이 걸릴 수 있습니다. 실패하면 잠시 후 다시 시도하세요.
