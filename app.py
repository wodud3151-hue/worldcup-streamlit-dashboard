import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


DATA_PATH = Path("pool.json")
LEGACY_DATA_PATH = Path("data/pool.json")
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

ROUNDS = [
    {"id": "r16", "label": "16강", "expected": 16},
    {"id": "qf", "label": "8강", "expected": 8},
    {"id": "sf", "label": "4강", "expected": 4},
    {"id": "champion", "label": "우승", "expected": 1},
]


st.set_page_config(
    page_title="월드컵 예측 대시보드",
    page_icon="🏆",
    layout="wide",
)


def normalize_team(team: str) -> str:
    return team.strip().lower()


def split_teams(text: str) -> list[str]:
    """쉼표, 줄바꿈, 세미콜론으로 입력된 팀명을 리스트로 변환한다."""
    raw = text.replace(";", ",").replace("\n", ",").split(",")
    teams = [item.strip() for item in raw if item.strip()]
    deduped = []
    seen = set()
    for team in teams:
        key = normalize_team(team)
        if key not in seen:
            deduped.append(team)
            seen.add(key)
    return deduped


def load_pool() -> dict:
    if not DATA_PATH.exists() and LEGACY_DATA_PATH.exists():
        return json.loads(LEGACY_DATA_PATH.read_text(encoding="utf-8"))

    if not DATA_PATH.exists():
        DATA_PATH.write_text(
            json.dumps(
                {
                    "title": "월드컵 예측 내기",
                    "admin_password": "admin",
                    "participants": [],
                    "results": {"r16": [], "qf": [], "sf": [], "champion": []},
                    "history": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def save_pool(pool: dict) -> None:
    DATA_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")


def count_hits(predictions: list[str], actual: list[str]) -> int:
    actual_set = {normalize_team(team) for team in actual}
    return sum(1 for team in predictions if normalize_team(team) in actual_set)


def round_winners(pool: dict, round_id: str) -> tuple[list[str], int]:
    actual = pool["results"].get(round_id, [])
    if not actual:
        return [], 0

    scores = []
    for participant in pool["participants"]:
        predictions = participant.get("predictions", {}).get(round_id, [])
        scores.append((participant["name"], count_hits(predictions, actual)))

    top_score = max([score for _, score in scores], default=0)
    if top_score == 0:
        return [], 0
    return [name for name, score in scores if score == top_score], top_score


def current_round(pool: dict) -> str:
    for item in ROUNDS:
        if len(pool["results"].get(item["id"], [])) < item["expected"]:
            return item["label"]
    return "완료"


def match_round_id(event: dict) -> str | None:
    competition = (event.get("competitions") or [{}])[0]
    text = " ".join(
        str(value)
        for value in [
            competition.get("name"),
            (competition.get("stage") or {}).get("description"),
            (competition.get("type") or {}).get("text"),
        ]
        if value
    ).lower()

    if "round of 16" in text or "16강" in text:
        return "r16"
    if "quarter" in text or "8강" in text:
        return "qf"
    if "semi" in text or "4강" in text:
        return "sf"
    if "final" in text or "championship" in text or "결승" in text:
        return "champion"
    return None


@st.cache_data(ttl=60)
def fetch_live_matches() -> tuple[list[dict], str | None]:
    """ESPN 공개 scoreboard를 조회한다. 실패하면 수동 입력을 계속 쓸 수 있게 오류만 반환한다."""
    try:
        response = requests.get(ESPN_SCOREBOARD_URL, params={"limit": 100}, timeout=8)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return [], str(exc)

    matches = []
    for event in data.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        teams = []
        for competitor in competitors:
            team = competitor.get("team") or {}
            teams.append(
                {
                    "name": team.get("displayName") or team.get("shortDisplayName") or "팀 미정",
                    "score": competitor.get("score", "0"),
                    "winner": bool(competitor.get("winner")),
                }
            )

        status = ((event.get("status") or {}).get("type") or {})
        matches.append(
            {
                "name": event.get("shortName") or event.get("name") or "경기",
                "date": event.get("date"),
                "status": status.get("description") or "상태 미정",
                "completed": bool(status.get("completed")),
                "round_id": match_round_id(event),
                "teams": teams,
            }
        )
    return matches, None


def apply_live_results(pool: dict, matches: list[dict]) -> dict:
    """완료/진행 경기 정보를 실제 진출팀 결과에 반영한다."""
    for match in matches:
        round_id = match.get("round_id")
        if not round_id:
            continue

        if round_id != "champion":
            current = pool["results"].get(round_id, [])
            pool["results"][round_id] = split_teams(", ".join(current + [team["name"] for team in match["teams"]]))

        if round_id == "champion" and match.get("completed"):
            winners = [team["name"] for team in match["teams"] if team["winner"]]
            if winners:
                pool["results"]["champion"] = winners[:1]
    return pool


def render_live_matches(pool: dict, is_admin: bool) -> None:
    st.subheader("실시간 경기 진행")
    matches, error = fetch_live_matches()

    top = st.columns([2, 1, 1])
    with top[0]:
        if error:
            st.warning(f"경기 데이터를 불러오지 못했습니다. 수동 결과 입력을 사용하세요. ({error})")
        else:
            st.caption(f"ESPN 공개 scoreboard 기준 · {datetime.now().strftime('%H:%M:%S')} 확인")
    with top[1]:
        if st.button("경기 새로고침", use_container_width=True):
            fetch_live_matches.clear()
            st.rerun()
    with top[2]:
        if is_admin and st.button("완료/진행 결과 반영", use_container_width=True):
            save_pool(apply_live_results(pool, matches))
            st.success("실시간 경기 데이터를 실제 결과에 반영했습니다.")
            st.rerun()

    if not matches:
        st.info("현재 scoreboard에 표시되는 월드컵 경기가 없습니다. 경기일에는 자동으로 표시됩니다.")
        return

    cols = st.columns(2)
    for idx, match in enumerate(matches):
        with cols[idx % 2]:
            round_label = next((item["label"] for item in ROUNDS if item["id"] == match.get("round_id")), "월드컵")
            with st.container(border=True):
                st.caption(f"{round_label} · {match['status']}")
                for team in match["teams"]:
                    mark = "✅ " if team["winner"] else ""
                    st.write(f"**{mark}{team['name']}**  {team['score']}")
                if match.get("date"):
                    st.caption(pd.to_datetime(match["date"]).strftime("%Y-%m-%d %H:%M"))


def render_dashboard(pool: dict) -> None:
    st.title(pool.get("title", "월드컵 예측 대시보드"))
    st.caption("친구들과 월드컵 예측 현황과 라운드별 승자를 보는 공유 대시보드")

    summary = st.columns(4)
    summary[0].metric("현재 라운드", current_round(pool))
    summary[1].metric("참가자", f"{len(pool['participants'])}명")
    entered = sum(len(pool["results"].get(item["id"], [])) for item in ROUNDS)
    total = sum(item["expected"] for item in ROUNDS)
    summary[2].metric("결과 입력", f"{entered}/{total}")
    summary[3].metric("저장 방식", "JSON MVP")

    st.subheader("라운드별 승자")
    winner_cols = st.columns(4)
    for col, item in zip(winner_cols, ROUNDS):
        winners, top_score = round_winners(pool, item["id"])
        with col:
            with st.container(border=True):
                st.write(f"**{item['label']}**")
                st.write(", ".join(winners) if winners else "대기 중")
                st.caption(f"최고 적중 {top_score}개")

    st.subheader("참가자별 예측/적중 현황")
    rows = []
    for participant in pool["participants"]:
        row = {"참가자": participant["name"], "총 골수": participant.get("tiebreaker_goals", "")}
        for item in ROUNDS:
            predictions = participant.get("predictions", {}).get(item["id"], [])
            actual = pool["results"].get(item["id"], [])
            hits = count_hits(predictions, actual) if actual else 0
            row[item["label"]] = f"{hits}개 적중 · " + (", ".join(predictions) if predictions else "미입력")
        rows.append(row)

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("아직 참가자가 없습니다.")

    st.subheader("실제 결과")
    result_cols = st.columns(4)
    for col, item in zip(result_cols, ROUNDS):
        with col:
            with st.container(border=True):
                st.write(f"**{item['label']}**")
                result = pool["results"].get(item["id"], [])
                st.write(", ".join(result) if result else "미입력")


def render_admin(pool: dict) -> None:
    st.sidebar.divider()
    st.sidebar.subheader("관리자")
    password = st.sidebar.text_input("관리자 비밀번호", type="password")
    is_admin = password == pool.get("admin_password", "admin")

    if not is_admin:
        st.sidebar.caption("조회는 누구나 가능하고, 수정은 관리자만 가능합니다.")
        return False

    st.sidebar.success("관리자 모드")

    with st.expander("참가자와 예측 수정", expanded=False):
        names_text = "\n".join(participant["name"] for participant in pool["participants"])
        names_new = st.text_area("참가자 이름 목록", value=names_text, height=120)

        existing = {participant["name"]: participant for participant in pool["participants"]}
        next_participants = []
        for name in [item.strip() for item in names_new.splitlines() if item.strip()]:
            next_participants.append(
                existing.get(
                    name,
                    {"name": name, "predictions": {item["id"]: [] for item in ROUNDS}},
                )
            )

        pool["participants"] = next_participants

        for participant in pool["participants"]:
            st.markdown(f"**{participant['name']}**")
            participant["tiebreaker_goals"] = st.number_input(
                f"{participant['name']} · 8강전 총 골수",
                min_value=0,
                max_value=99,
                value=int(participant.get("tiebreaker_goals") or 0),
                key=f"goals-{participant['name']}",
            )
            for item in ROUNDS:
                current = ", ".join(participant.get("predictions", {}).get(item["id"], []))
                value = st.text_input(
                    f"{participant['name']} · {item['label']} 예측",
                    value=current,
                    key=f"pred-{participant['name']}-{item['id']}",
                )
                participant.setdefault("predictions", {})[item["id"]] = split_teams(value)

        if st.button("참가자/예측 저장", use_container_width=True):
            save_pool(pool)
            st.success("저장했습니다.")
            st.rerun()

    with st.expander("실제 결과 직접 수정", expanded=False):
        for item in ROUNDS:
            current = ", ".join(pool["results"].get(item["id"], []))
            value = st.text_area(f"{item['label']} 실제 결과", value=current, key=f"result-{item['id']}")
            pool["results"][item["id"]] = split_teams(value)

        if st.button("실제 결과 저장", use_container_width=True):
            save_pool(pool)
            st.success("저장했습니다.")
            st.rerun()

    with st.expander("내기 이력 저장", expanded=False):
        title = st.text_input("이력 제목", value=f"{datetime.now().strftime('%Y-%m-%d')} 내기 기록")
        if st.button("현재 승자 이력 저장", use_container_width=True):
            snapshot = {
                "title": title,
                "created_at": datetime.now().isoformat(),
                "winners": {},
            }
            for item in ROUNDS:
                winners, top_score = round_winners(pool, item["id"])
                snapshot["winners"][item["id"]] = {"names": winners, "top_score": top_score}
            pool.setdefault("history", []).insert(0, snapshot)
            save_pool(pool)
            st.success("이력을 저장했습니다.")
            st.rerun()

    return True


pool = load_pool()
is_admin = render_admin(pool)

render_live_matches(pool, is_admin)
render_dashboard(pool)

with st.expander("과거 내기 이력", expanded=False):
    if not pool.get("history"):
        st.caption("저장된 이력이 없습니다.")
    for item in pool.get("history", []):
        st.write(f"**{item['title']}**")
        for round_item in ROUNDS:
            winner = item["winners"].get(round_item["id"], {})
            names = ", ".join(winner.get("names", [])) or "대기 중"
            st.caption(f"{round_item['label']}: {names} ({winner.get('top_score', 0)}개)")
