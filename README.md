# 월드컵 예측 대시보드 Streamlit MVP

친구들에게 공유 가능한 URL로 월드컵 예측 현황을 보여주는 Streamlit 앱입니다.

## 바로 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 배포

1. GitHub에 새 저장소를 만듭니다.
2. 이 폴더의 `app.py`, `requirements.txt`, `data/pool.json`을 업로드합니다.
3. https://share.streamlit.io 또는 Streamlit Community Cloud에 접속합니다.
4. `Create app`을 누르고 GitHub 저장소, 브랜치, `app.py`를 선택합니다.
5. Deploy 후 생성된 URL을 친구들에게 공유합니다.

## 운영

- 친구들은 URL로 조회합니다.
- 관리자는 왼쪽 사이드바에서 비밀번호를 입력합니다.
- 기본 비밀번호는 `admin`입니다.
- 관리자 모드에서 친구 이름, 예측, 실제 결과를 수정할 수 있습니다.
- 실시간 경기 진행은 ESPN 공개 scoreboard를 조회합니다.
- 경기 데이터가 불안정하면 실제 결과를 직접 입력하면 됩니다.

## 데이터 입력 형식

팀 목록은 쉼표 또는 줄바꿈으로 입력합니다.

```text
한국, 브라질, 프랑스, 아르헨티나
```

## 주의

Streamlit Community Cloud에서 파일 저장은 앱 재시작/재배포 시 초기화될 수 있습니다. 처음 MVP 검증에는 충분하지만, 실제 운영을 안정적으로 하려면 Google Sheets 또는 Supabase 저장소를 붙이는 것을 추천합니다.
