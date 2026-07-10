import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


DATA_PATH = Path("pool.json")
LEGACY_DATA_PATH = Path("data/pool.json")
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

ROUND_DEFS = {
    "qf": {"label": "8강전", "games": ["1경기", "2경기", "3경기", "4경기"]},
    "r16": {"label": "16강전", "games": ["1경기", "2경기", "3경기", "4경기"]},
    "champion": {"label": "우승팀", "games": ["우승팀"]},
}


st.set_page_config(
    page_title="월드컵 예측 대시보드",
    page_icon="🏆",
    layout="wide",
)


CUSTOM_CSS = """
<style>
.block-container { padding-top: 1.5rem; }
.match-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 8px 0 18px;
}
.match-card {
  border: 1px solid #d7dee8;
  border-radius: 8px;
  background: #fff;
  min-height: 112px;
  padding: 10px 12px;
}
.match-card.live { border-color: #f3c363; background: #fff8e8; }
.match-card.result { border-color: #a9e3c4; background: #f0fbf5; }
.match-kicker { color: #667085; font-size: 12px; font-weight: 700; margin-bottom: 4px; }
.match-title { font-size: 17px; font-weight: 900; margin-bottom: 4px; }
.match-note { color: #667085; font-size: 13px; }
.winner-box {
  border: 1px solid #a9e3c4;
  background: #f0fbf5;
  color: #0b4b32;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0 12px;
  font-weight: 900;
}
.prediction-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 14px;
  margin-bottom: 18px;
}
.prediction-table th,
.prediction-table td {
  border: 1px solid #d7dee8;
  text-align: center;
  vertical-align: middle;
  padding: 7px 6px;
  line-height: 1.25;
  word-break: keep-all;
}
.prediction-table th {
  background: #f3f6f9;
  color: #263241;
  font-weight: 900;
}
.prediction-table .game-cell {
  background: #f8fafc;
  font-weight: 900;
  width: 76px;
}
.prediction-table .actual-cell {
  background: #eef6ff;
  color: #24527a;
  font-weight: 900;
  width: 90px;
}
.prediction-table .hit {
  background: #dff6ea;
  color: #11683e;
  font-weight: 900;
}
.prediction-table .miss {
  background: #ffe4df;
  color: #9f2d20;
  font-weight: 800;
}
.prediction-table .pending {
  background: #fff;
  color: #263241;
}
.score-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 8px;
}
.score-table th,
.score-table td {
  border: 1px solid #d7dee8;
  text-align: center;
  padding: 6px;
}
.score-table th { background: #f3f6f9; }
@media (max-width: 900px) {
  .match-strip { grid-template-columns: 1fr; }
  .prediction-table { font-size: 12px; }
  .prediction-table th,
  .prediction-table td { padding: 6px 4px; }
}
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
        "featured": {
            "recent": {"title": "최근 경기 결과", "summary": "결과 입력 전", "detail": ""},
            "next": {"title": "다음 예정 경기", "summary": "스페인 vs 벨기에", "detail": ""},
        },
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
    pool.setdefault("featured", default_pool()["featured"])
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
    return sum(
        1
        for idx, _ in enumerate(ROUND_DEFS[round_id]["games"])
        if is_hit(prediction_for(participant, round_id, idx), actual_for(pool, round_id, idx))
    )


def round_winners(pool: dict, round_id: str) -> tuple[list[str], int]:
    if not any(pool.get("results", {}).get(round_id, [])):
        return [], 0
    scores = [
        (participant["name"], participant_score(pool, participant, round_id))
        for participant in pool.get("participants", [])
    ]
    top_score = max([score for _, score in scores], default=0)
    if top_score == 0:
        return [], 0
    return [name for name, score in scores if score == top_score], top_score


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
        matches.append(
            {
                "name": event.get("shortName") or event.get("name") or "경기",
                "date": event.get("date"),
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
    return not match.get("completed") and any(key in status_name for key in ["IN_PROGRESS", "HALFTIME", "LIVE"])


def is_upcoming_match(match: dict) -> bool:
    if match.get("completed") or is_live_match(match):
        return False
    match_dt = parse_dt(match.get("date"))
    if match_dt is None:
        return True
    if match_dt.tzinfo is None:
        match_dt = match_dt.replace(tzinfo=timezone.utc)
    return match_dt >= datetime.now(timezone.utc)


def sort_key(match: dict):
    return parse_dt(match.get("date")) or datetime.max.replace(tzinfo=timezone.utc)


def match_summary(match: dict) -> str:
    teams = match.get("teams", [])
    if len(teams) >= 2:
        return f"{teams[0]['name']} {teams[0]['score']} - {teams[1]['score']} {teams[1]['name']}"
    return match.get("name", "경기")


def render_match_block(kind: str, title: str, summary: str, detail: str = "") -> str:
    css_kind = "live" if kind == "live" else "result" if kind == "result" else ""
    return f"""
    <div class="match-card {css_kind}">
      <div class="match-kicker">{title}</div>
      <div class="match-title">{summary}</div>
      <div class="match-note">{detail}</div>
    </div>
    """


def render_match_card(kind: str, title: str, summary: str, detail: str = "") -> None:
    st.markdown(render_match_block(kind, title, summary, detail), unsafe_allow_html=True)


def render_match_overview(pool: dict) -> None:
    matches, error = fetch_live_matches()
    live_matches = []
    completed_matches = []
    upcoming_matches = []

    if not error:
        live_matches = [match for match in matches if is_live_match(match)]
        completed_matches = sorted(
            [match for match in matches if match.get("completed")],
            key=sort_key,
            reverse=True,
        )
        upcoming_matches = sorted(
            [match for match in matches if is_upcoming_match(match)],
            key=sort_key,
        )

    featured = pool.get("featured", {})
    recent = featured.get("recent", {})
    next_match = featured.get("next", {})

    cols = st.columns(3)
    with cols[0]:
        render_match_card(
            "result",
            "가장 최근 경기 결과",
            match_summary(completed_matches[0]) if completed_matches else recent.get("summary", "프랑스 2 - 0 모로코"),
            completed_matches[0].get("status", "") if completed_matches else recent.get("detail", "득점: 음바페, 뎀벨레"),
        )
    with cols[1]:
        render_match_card(
            "live",
            "현재 하고있는 매치",
            match_summary(live_matches[0]) if live_matches else "진행 중인 경기 없음",
            live_matches[0].get("status", "8강전 진행 상황은 자동 갱신됩니다.") if live_matches else "8강전 진행 상황은 자동 갱신됩니다.",
        )
    with cols[2]:
        render_match_card(
            "",
            "다음 예정 경기",
            match_summary(upcoming_matches[0]) if upcoming_matches else next_match.get("summary", "스페인 vs 벨기에"),
            upcoming_matches[0].get("status", "") if upcoming_matches else next_match.get("detail", "8강 2경기 예정"),
        )


def cell_class(pick: str, actual: str) -> str:
    if not actual:
        return "pending"
    return "hit" if is_hit(pick, actual) else "miss"


def render_prediction_table(pool: dict, round_id: str) -> None:
    round_def = ROUND_DEFS[round_id]
    participants = pool.get("participants", [])
    winners, top_score = round_winners(pool, round_id)

    st.subheader(round_def["label"])
    if winners:
        st.markdown(
            f'<div class="winner-box">{round_def["label"]} 승자: {", ".join(winners)} · {top_score}개 적중</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("결과가 입력되면 맞춘 선택이 색칠되고 승자가 표시됩니다.")

    score_cells = "".join(
        f"<td><b>{participant_score(pool, participant, round_id)}</b></td>"
        for participant in participants
    )
    goal_cells = "".join(
        f"<td>{participant.get('tiebreaker_goals', '') if round_id == 'qf' else ''}</td>"
        for participant in participants
    )
    header_cells = "".join(
        f"<th>{participant['name']}{' 🏆' if participant['name'] in winners else ''}</th>"
        for participant in participants
    )

    html = f"""
    <table class="score-table">
      <tr><th>구분</th>{header_cells}</tr>
      <tr><td>적중 수</td>{score_cells}</tr>
      {"<tr><td>총 골수</td>" + goal_cells + "</tr>" if round_id == "qf" else ""}
    </table>
    <table class="prediction-table">
      <tr>
        <th class="game-cell">경기</th>
        <th class="actual-cell">결과</th>
        {header_cells}
      </tr>
    """

    for game_index, game_label in enumerate(round_def["games"]):
        actual = actual_for(pool, round_id, game_index)
        html += f'<tr><td class="game-cell">{game_label}</td><td class="actual-cell">{actual or "진행/대기"}</td>'
        for participant in participants:
            pick = prediction_for(participant, round_id, game_index)
            html += f'<td class="{cell_class(pick, actual)}">{pick or "미입력"}</td>'
        html += "</tr>"

    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)


def render_bottom_stats(pool: dict) -> None:
    st.subheader("누적 승리/적중 현황")
    participants = pool.get("participants", [])
    past_wins = pool.get("past_wins", {})
    round_win_counts = {participant["name"]: int(past_wins.get(participant["name"], 0)) for participant in participants}

    for round_id in ["r16", "qf", "champion"]:
        winners, _ = round_winners(pool, round_id)
        for winner in winners:
            round_win_counts[winner] = round_win_counts.get(winner, 0) + 1

    rows = []
    for participant in participants:
        rows.append(
            {
                "이름": participant["name"],
                "16강 적중": participant_score(pool, participant, "r16"),
                "8강 적중": participant_score(pool, participant, "qf"),
                "라운드 승리": round_win_counts.get(participant["name"], 0),
            }
        )

    if not rows:
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.bar_chart(df.set_index("이름")[["16강 적중", "8강 적중", "라운드 승리"]])


def render_champion(pool: dict) -> None:
    st.subheader("우승팀 예측")
    participants = pool.get("participants", [])
    actual = actual_for(pool, "champion", 0)
    winners, top_score = round_winners(pool, "champion")
    if winners:
        st.markdown(
            f'<div class="winner-box">우승팀 예측 승자: {", ".join(winners)} · {top_score}개 적중</div>',
            unsafe_allow_html=True,
        )

    header_cells = "".join(f"<th>{participant['name']}</th>" for participant in participants)
    pick_cells = ""
    for participant in participants:
        pick = prediction_for(participant, "champion", 0)
        pick_cells += f'<td class="{cell_class(pick, actual)}">{pick or "미입력"}</td>'
    html = f"""
    <table class="prediction-table">
      <tr><th class="actual-cell">결과</th>{header_cells}</tr>
      <tr><td class="actual-cell">{actual or "대기"}</td>{pick_cells}</tr>
    </table>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_admin(pool: dict) -> bool:
    st.sidebar.subheader("관리자")
    password = st.sidebar.text_input("관리자 비밀번호", type="password")
    is_admin = password == pool.get("admin_password", "admin")
    if not is_admin:
        st.sidebar.caption("조회는 누구나 가능하고, 수정은 관리자만 가능합니다.")
        return False

    st.sidebar.success("관리자 모드")
    with st.sidebar.expander("실제 결과 수정", expanded=True):
        for round_id in ["qf", "r16", "champion"]:
            current = ", ".join(pool.get("results", {}).get(round_id, []))
            value = st.text_area(
                f"{ROUND_DEFS[round_id]['label']} 결과",
                value=current,
                help="1경기, 2경기, 3경기, 4경기 순서대로 쉼표로 입력",
                key=f"result-{round_id}",
            )
            pool.setdefault("results", {})[round_id] = split_teams(value)

        if st.button("실제 결과 저장", use_container_width=True):
            save_pool(pool)
            st.success("저장했습니다.")
            st.rerun()

    with st.sidebar.expander("상단 경기 카드 수정", expanded=False):
        pool.setdefault("featured", default_pool()["featured"])
        recent = pool["featured"].setdefault("recent", {})
        next_match = pool["featured"].setdefault("next", {})
        recent["summary"] = st.text_input("최근 경기 결과", recent.get("summary", "프랑스 승리"))
        recent["detail"] = st.text_input("최근 경기 설명", recent.get("detail", "8강 1경기 결과"))
        next_match["summary"] = st.text_input("다음 예정 경기", next_match.get("summary", "스페인 vs 벨기에"))
        next_match["detail"] = st.text_input("다음 경기 설명", next_match.get("detail", "8강 2경기 예정"))
        if st.button("상단 카드 저장", use_container_width=True):
            save_pool(pool)
            st.success("저장했습니다.")
            st.rerun()

    return True


st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
pool = load_pool()
render_admin(pool)

st.title(pool.get("title", "월드컵 예측 대시보드"))
st.caption("8강 진행 상황을 최상단에 두고, 라운드별 선택과 적중 여부를 표로 확인합니다.")

render_match_overview(pool)
render_prediction_table(pool, "qf")
st.divider()
render_prediction_table(pool, "r16")
st.divider()
render_champion(pool)
st.divider()
render_bottom_stats(pool)
