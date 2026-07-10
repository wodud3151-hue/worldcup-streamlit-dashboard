import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


DATA_PATH = Path("pool.json")
LEGACY_DATA_PATH = Path("data/pool.json")
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

ROUNDS = [
    {"id": "r16", "label": "16강전", "games": ["1경기", "2경기", "3경기", "4경기"]},
    {"id": "qf", "label": "8강전", "games": ["1경기", "2경기", "3경기", "4경기"]},
    {"id": "champion", "label": "우승팀", "games": ["우승팀"]},
]


st.set_page_config(
    page_title="월드컵 예측 대시보드",
    page_icon="🏆",
    layout="wide",
)


CUSTOM_CSS = """
<style>
.pick-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 5px 10px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 0.92rem;
  margin: 2px 0;
}
.pick-hit { background: #dff6ea; color: #11683e; border: 1px solid #a9e3c4; }
.pick-miss { background: #ffe4df; color: #9f2d20; border: 1px solid #f1afa5; }
.pick-pending { background: #edf1f5; color: #526071; border: 1px solid #d7dee8; }
.winner-box {
  border: 1px solid #a9e3c4;
  background: #f0fbf5;
  color: #0b4b32;
  border-radius: 10px;
  padding: 14px 16px;
  margin: 10px 0 18px;
  font-weight: 800;
}
.match-now {
  border: 1px solid #f3c363;
  background: #fff8e8;
  border-radius: 10px;
  padding: 14px 16px;
}
.match-next {
  border: 1px solid #d7dee8;
  background: #ffffff;
  border-radius: 10px;
  padding: 14px 16px;
}
.muted-small { color: #667085; font-size: 0.88rem; }
</style>
"""


def normalize_team(team: str) -> str:
    return str(team).strip().lower()


def split_teams(text: str) -> list[str]:
    raw = str(text).replace(";", ",").replace("\n", ",").split(",")
    return [item.strip() for item in raw if item.strip()]


def default_pool() -> dict:
    return {
        "title": "월드컵 예측 내기",
        "admin_password": "admin",
        "participants": [],
        "results": {"r16": [], "qf": [], "champion": []},
        "history": [],
    }


def load_pool() -> dict:
    if DATA_PATH.exists():
        pool = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    elif LEGACY_DATA_PATH.exists():
        pool = json.loads(LEGACY_DATA_PATH.read_text(encoding="utf-8"))
    else:
        pool = default_pool()
        save_pool(pool)

    pool.setdefault("results", {"r16": [], "qf": [], "champion": []})
    pool.setdefault("history", [])
    for participant in pool.setdefault("participants", []):
        participant.setdefault("predictions", {})
        participant.setdefault("tiebreaker_goals", "")
    return pool


def save_pool(pool: dict) -> None:
    DATA_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")


def prediction_for(participant: dict, round_id: str, game_index: int) -> str:
    picks = participant.get("predictions", {}).get(round_id, [])
    return picks[game_index] if game_index < len(picks) else ""


def actual_for(pool: dict, round_id: str, game_index: int) -> str:
    actual = pool.get("results", {}).get(round_id, [])
    return actual[game_index] if game_index < len(actual) else ""


def is_hit(pick: str, actual: str) -> bool:
    return bool(pick and actual and normalize_team(pick) == normalize_team(actual))


def participant_score(pool: dict, participant: dict, round_id: str) -> int:
    round_def = next(item for item in ROUNDS if item["id"] == round_id)
    return sum(
        1
        for idx, _ in enumerate(round_def["games"])
        if is_hit(prediction_for(participant, round_id, idx), actual_for(pool, round_id, idx))
    )


def round_winners(pool: dict, round_id: str) -> tuple[list[str], int]:
    actual_values = [team for team in pool.get("results", {}).get(round_id, []) if team]
    if not actual_values:
        return [], 0

    scores = [
        (participant["name"], participant_score(pool, participant, round_id))
        for participant in pool.get("participants", [])
    ]
    top_score = max([score for _, score in scores], default=0)
    if top_score == 0:
        return [], 0
    return [name for name, score in scores if score == top_score], top_score


def chip_html(text: str, status: str) -> str:
    safe_text = text or "미입력"
    return f'<span class="pick-chip pick-{status}">{safe_text}</span>'


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
    try:
        response = requests.get(ESPN_SCOREBOARD_URL, params={"limit": 100}, timeout=8)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return [], str(exc)

    matches = []
    for event in data.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        teams = []
        for competitor in competition.get("competitors") or []:
            team = competitor.get("team") or {}
            teams.append(
                {
                    "name": team.get("displayName") or team.get("shortDisplayName") or "팀 미정",
                    "score": competitor.get("score", "0"),
                    "winner": bool(competitor.get("winner")),
                }
            )

        status = ((event.get("status") or {}).get("type") or {})
        date_value = event.get("date")
        matches.append(
            {
                "name": event.get("shortName") or event.get("name") or "경기",
                "date": date_value,
                "status": status.get("description") or "상태 미정",
                "status_name": status.get("name") or "",
                "completed": bool(status.get("completed")),
                "round_id": match_round_id(event),
                "teams": teams,
            }
        )
    return matches, None


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None


def is_live_match(match: dict) -> bool:
    status_name = str(match.get("status_name", "")).upper()
    if match.get("completed"):
        return False
    return any(key in status_name for key in ["IN_PROGRESS", "HALFTIME", "LIVE"])


def is_upcoming_match(match: dict) -> bool:
    if match.get("completed") or is_live_match(match):
        return False
    match_dt = parse_dt(match.get("date"))
    if match_dt is None:
        return True
    now = datetime.now(timezone.utc)
    if match_dt.tzinfo is None:
        match_dt = match_dt.replace(tzinfo=timezone.utc)
    return match_dt >= now


def render_match_card(match: dict, css_class: str) -> None:
    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
    st.caption(match.get("status", "상태 미정"))
    st.write(f"**{match.get('name', '경기')}**")
    for team in match.get("teams", []):
        mark = "✅ " if team.get("winner") else ""
        st.write(f"{mark}{team['name']}  **{team['score']}**")
    match_dt = parse_dt(match.get("date"))
    if match_dt:
        st.caption(match_dt.strftime("%Y-%m-%d %H:%M"))
    st.markdown("</div>", unsafe_allow_html=True)


def render_live_overview() -> None:
    st.subheader("현재 하고있는 매치")
    matches, error = fetch_live_matches()
    if error:
        st.warning(f"실시간 경기 데이터를 불러오지 못했습니다. 수동 결과 입력을 사용하세요. ({error})")
        return

    live_matches = [match for match in matches if is_live_match(match)]
    upcoming_matches = sorted(
        [match for match in matches if is_upcoming_match(match)],
        key=lambda item: parse_dt(item.get("date")) or datetime.max,
    )
    completed_matches = [match for match in matches if match.get("completed")]

    if live_matches:
        cols = st.columns(min(2, len(live_matches)))
        for idx, match in enumerate(live_matches):
            with cols[idx % len(cols)]:
                render_match_card(match, "match-now")
    else:
        st.info("지금 진행 중인 월드컵 경기는 없습니다.")

    st.subheader("다음 경기")
    if upcoming_matches:
        cols = st.columns(min(3, len(upcoming_matches[:6])))
        for idx, match in enumerate(upcoming_matches[:6]):
            with cols[idx % len(cols)]:
                render_match_card(match, "match-next")
    else:
        st.caption("표시할 예정 경기가 없습니다.")

    with st.expander("완료된 경기 결과", expanded=False):
        if not completed_matches:
            st.caption("표시할 완료 경기가 없습니다.")
        for match in completed_matches[:10]:
            render_match_card(match, "match-next")


def render_round_section(pool: dict, round_id: str) -> None:
    round_def = next(item for item in ROUNDS if item["id"] == round_id)
    st.subheader(round_def["label"])

    winners, top_score = round_winners(pool, round_id)
    if winners:
        st.markdown(
            f'<div class="winner-box">{round_def["label"]} 승자: {", ".join(winners)} · {top_score}개 적중</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("실제 결과가 입력되면 라운드 승자가 자동으로 표시됩니다.")

    score_rows = []
    for participant in pool.get("participants", []):
        score_rows.append(
            {
                "이름": participant["name"],
                "적중 수": participant_score(pool, participant, round_id),
                "총 골수": participant.get("tiebreaker_goals", "") if round_id == "qf" else "",
            }
        )
    if score_rows:
        st.dataframe(pd.DataFrame(score_rows), use_container_width=True, hide_index=True)

    game_cols = st.columns(2)
    for game_index, game_label in enumerate(round_def["games"]):
        actual = actual_for(pool, round_id, game_index)
        with game_cols[game_index % 2]:
            with st.container(border=True):
                st.markdown(f"### {game_label}")
                st.caption(f"실제 결과: {actual or '미입력'}")
                for participant in pool.get("participants", []):
                    pick = prediction_for(participant, round_id, game_index)
                    if actual:
                        status = "hit" if is_hit(pick, actual) else "miss"
                    else:
                        status = "pending"
                    st.markdown(
                        f"**{participant['name']}** &nbsp; {chip_html(pick, status)}",
                        unsafe_allow_html=True,
                    )


def render_champion_section(pool: dict) -> None:
    st.subheader("우승팀 예측")
    actual = actual_for(pool, "champion", 0)
    winners, top_score = round_winners(pool, "champion")
    if winners:
        st.markdown(
            f'<div class="winner-box">우승팀 예측 승자: {", ".join(winners)} · {top_score}개 적중</div>',
            unsafe_allow_html=True,
        )

    cols = st.columns(3)
    for idx, participant in enumerate(pool.get("participants", [])):
        with cols[idx % 3]:
            pick = prediction_for(participant, "champion", 0)
            status = "hit" if actual and is_hit(pick, actual) else "miss" if actual else "pending"
            with st.container(border=True):
                st.write(f"**{participant['name']}**")
                st.markdown(chip_html(pick, status), unsafe_allow_html=True)


def render_admin(pool: dict) -> bool:
    st.sidebar.subheader("관리자")
    password = st.sidebar.text_input("관리자 비밀번호", type="password")
    is_admin = password == pool.get("admin_password", "admin")
    if not is_admin:
        st.sidebar.caption("조회는 누구나 가능하고, 수정은 관리자만 가능합니다.")
        return False

    st.sidebar.success("관리자 모드")

    with st.sidebar.expander("실제 결과 수정", expanded=True):
        for round_def in ROUNDS:
            current = ", ".join(pool.get("results", {}).get(round_def["id"], []))
            value = st.text_area(
                f"{round_def['label']} 결과",
                value=current,
                help="1경기, 2경기, 3경기, 4경기 순서대로 쉼표로 입력",
                key=f"result-{round_def['id']}",
            )
            pool.setdefault("results", {})[round_def["id"]] = split_teams(value)

        if st.button("실제 결과 저장", use_container_width=True):
            save_pool(pool)
            st.success("저장했습니다.")
            st.rerun()

    with st.sidebar.expander("참가자/예측 수정", expanded=False):
        names = "\n".join(item["name"] for item in pool.get("participants", []))
        next_names = st.text_area("참가자 이름", names, height=120)
        existing = {item["name"]: item for item in pool.get("participants", [])}
        pool["participants"] = [
            existing.get(name, {"name": name, "predictions": {}, "tiebreaker_goals": ""})
            for name in [line.strip() for line in next_names.splitlines() if line.strip()]
        ]

        for participant in pool["participants"]:
            st.markdown(f"**{participant['name']}**")
            participant["tiebreaker_goals"] = st.number_input(
                f"{participant['name']} 총 골수",
                min_value=0,
                max_value=99,
                value=int(participant.get("tiebreaker_goals") or 0),
                key=f"goals-{participant['name']}",
            )
            for round_def in ROUNDS:
                current = ", ".join(participant.get("predictions", {}).get(round_def["id"], []))
                value = st.text_input(
                    f"{participant['name']} · {round_def['label']}",
                    value=current,
                    key=f"pred-{participant['name']}-{round_def['id']}",
                )
                participant.setdefault("predictions", {})[round_def["id"]] = split_teams(value)

        if st.button("참가자/예측 저장", use_container_width=True):
            save_pool(pool)
            st.success("저장했습니다.")
            st.rerun()

    return True


st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
pool = load_pool()
is_admin = render_admin(pool)

st.title(pool.get("title", "월드컵 예측 대시보드"))
st.caption("라운드별 경기 선택, 적중 현황, 실시간 경기 진행을 한 화면에서 보는 대시보드")

render_live_overview()
st.divider()
render_round_section(pool, "r16")
st.divider()
render_round_section(pool, "qf")
st.divider()
render_champion_section(pool)
