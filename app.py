import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh


DATA_PATH = Path("pool.json")
LEGACY_DATA_PATH = Path("data/pool.json")
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
AUTO_REFRESH_MS = 60_000

TEAM_NAME_MAP = {
    "Argentina": "아르헨티나",
    "ARG": "아르헨티나",
    "Belgium": "벨기에",
    "BEL": "벨기에",
    "Brazil": "브라질",
    "BRA": "브라질",
    "Colombia": "콜롬비아",
    "COL": "콜롬비아",
    "England": "잉글랜드",
    "ENG": "잉글랜드",
    "France": "프랑스",
    "FRA": "프랑스",
    "Germany": "독일",
    "GER": "독일",
    "Mexico": "멕시코",
    "MEX": "멕시코",
    "Morocco": "모로코",
    "MAR": "모로코",
    "Norway": "노르웨이",
    "NOR": "노르웨이",
    "Portugal": "포르투갈",
    "POR": "포르투갈",
    "Spain": "스페인",
    "ESP": "스페인",
    "Switzerland": "스위스",
    "SUI": "스위스",
    "United States": "미국",
    "USA": "미국",
}

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
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 6px 0 12px;
}
.match-card {
  border: 1px solid #d7dee8;
  border-radius: 8px;
  background: #fff;
  min-height: 82px;
  padding: 8px 10px;
}
.match-card.live { border-color: #f3c363; background: #fff8e8; }
.match-card.result { border-color: #a9e3c4; background: #f0fbf5; }
.match-kicker { color: #667085; font-size: 12px; font-weight: 700; margin-bottom: 4px; }
.match-title { font-size: 16px; font-weight: 900; margin-bottom: 3px; }
.match-note { color: #667085; font-size: 12px; }
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
  font-size: 13px;
  margin-bottom: 12px;
}
.prediction-table th,
.prediction-table td {
  border: 1px solid #d7dee8;
  text-align: center;
  vertical-align: middle;
  padding: 6px 4px;
  line-height: 1.18;
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
  width: 46px;
}
.prediction-table .actual-cell {
  background: #eef6ff;
  color: #24527a;
  font-weight: 900;
  width: 58px;
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
  font-size: 12px;
  margin-bottom: 6px;
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
  .prediction-table { font-size: 11px; }
  .prediction-table th,
  .prediction-table td { padding: 5px 2px; }
  .prediction-table .game-cell { width: 34px; }
  .prediction-table .actual-cell { width: 44px; }
  .score-table { font-size: 11px; }
  h1 { font-size: 1.75rem !important; }
  h2, h3 { margin-top: 0.35rem !important; }
}
</style>
"""


def normalize_team(team: str) -> str:
    return str(team).strip().lower()


def display_team(team: str) -> str:
    text = str(team).strip()
    return TEAM_NAME_MAP.get(text) or TEAM_NAME_MAP.get(text.upper()) or TEAM_NAME_MAP.get(text.title()) or text


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


def is_round_complete(pool: dict, round_id: str) -> bool:
    actual = [team for team in pool.get("results", {}).get(round_id, []) if team]
    if round_id in ["r16", "qf"]:
        if len(actual) < len(ROUND_DEFS[round_id]["games"]):
            return False
        if round_id == "qf":
            total_goals = pool.get("result_total_goals", {}).get("qf")
            return total_goals not in [None, ""]
        return True
    return bool(actual)


def round_winners(pool: dict, round_id: str) -> tuple[list[str], int]:
    if not is_round_complete(pool, round_id):
        return [], 0
    scores = [
        (participant["name"], participant_score(pool, participant, round_id))
        for participant in pool.get("participants", [])
    ]
    top_score = max([score for _, score in scores], default=0)
    if top_score == 0:
        return [], 0
    tied_names = [name for name, score in scores if score == top_score]

    if round_id == "qf" and len(tied_names) > 1:
        total_goals = pool.get("result_total_goals", {}).get("qf")
        if total_goals not in [None, ""]:
            participants_by_name = {participant["name"]: participant for participant in pool.get("participants", [])}
            distances = []
            for name in tied_names:
                predicted_goals = int(participants_by_name[name].get("tiebreaker_goals") or 0)
                distances.append((name, abs(predicted_goals - int(total_goals))))
            best_distance = min(distance for _, distance in distances)
            tied_names = [name for name, distance in distances if distance == best_distance]

    return tied_names, top_score


def winner_reason(pool: dict, round_id: str, top_score: int) -> str:
    if round_id != "qf":
        return f"{top_score}개 적중"

    total_goals = pool.get("result_total_goals", {}).get("qf")
    if total_goals in [None, ""]:
        return f"{top_score}개 적중 · 총 골수 결과 대기"
    return f"{top_score}개 적중 · 총 골수 {total_goals} 기준"


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


def translated_team_names(match: dict) -> list[str]:
    return [display_team(team.get("name", "")) for team in match.get("teams", [])]


def fixture_match_index(pool: dict, match: dict) -> int | None:
    match_teams = {normalize_team(team) for team in translated_team_names(match)}
    for idx, fixture in enumerate(pool.get("fixtures", {}).get("qf", [])):
        fixture_teams = {normalize_team(team) for team in fixture}
        if fixture_teams and fixture_teams.issubset(match_teams):
            return idx
    return None


def fixture_summary(pool: dict, idx: int) -> str:
    fixtures = pool.get("fixtures", {}).get("qf", [])
    if idx >= len(fixtures) or len(fixtures[idx]) < 2:
        return "다음 경기 대기"
    return f"{fixtures[idx][0]} vs {fixtures[idx][1]}"


def match_winner(match: dict) -> str:
    for team in match.get("teams", []):
        if team.get("winner"):
            return display_team(team.get("name", ""))
    teams = match.get("teams", [])
    if len(teams) >= 2:
        try:
            first_score = int(teams[0].get("score") or 0)
            second_score = int(teams[1].get("score") or 0)
        except ValueError:
            return ""
        if first_score > second_score:
            return display_team(teams[0].get("name", ""))
        if second_score > first_score:
            return display_team(teams[1].get("name", ""))
    return ""


def match_total_goals(match: dict) -> int:
    total = 0
    for team in match.get("teams", []):
        try:
            total += int(team.get("score") or 0)
        except ValueError:
            pass
    return total


def auto_apply_live_results(pool: dict, matches: list[dict]) -> dict:
    """Reflect completed quarterfinal results in the displayed table.

    The app keeps pool.json as the source of manual data, but on each refresh it
    overlays confirmed live results so viewers see the current state without
    waiting for a manual edit.
    """
    qf_fixtures = pool.get("fixtures", {}).get("qf", [])
    qf_results = list(pool.get("results", {}).get("qf", []))
    qf_completed_goal_totals = []

    for match in matches:
        idx = fixture_match_index(pool, match)
        if idx is None:
            continue

        if match.get("completed"):
            winner = match_winner(match)
            if winner:
                while len(qf_results) <= idx:
                    qf_results.append("")
                qf_results[idx] = winner
            qf_completed_goal_totals.append(match_total_goals(match))

    if qf_results:
        pool.setdefault("results", {})["qf"] = qf_results

    if len(qf_completed_goal_totals) == len(qf_fixtures) and qf_fixtures:
        pool.setdefault("result_total_goals", {})["qf"] = sum(qf_completed_goal_totals)

    return pool


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
        return f"{display_team(teams[0]['name'])} {teams[0]['score']} - {teams[1]['score']} {display_team(teams[1]['name'])}"
    return match.get("name", "경기")


def latest_completed_fixture_match(pool: dict, matches: list[dict]) -> dict | None:
    completed = [match for match in matches if match.get("completed") and fixture_match_index(pool, match) is not None]
    if not completed:
        return None
    return sorted(completed, key=sort_key, reverse=True)[0]


def next_fixture_match(pool: dict, matches: list[dict]) -> tuple[str, str]:
    results = pool.get("results", {}).get("qf", [])
    for idx, _fixture in enumerate(pool.get("fixtures", {}).get("qf", [])):
        if idx < len(results) and results[idx]:
            continue

        matched = [
            match for match in matches
            if fixture_match_index(pool, match) == idx and not match.get("completed")
        ]
        if matched:
            match = sorted(matched, key=sort_key)[0]
            match_dt = parse_dt(match.get("date"))
            detail = match.get("status", "")
            if match_dt:
                detail = f"{match_dt.strftime('%m월 %d일 %H:%M')} 예정"
            return fixture_summary(pool, idx), detail

        featured_next = pool.get("featured", {}).get("next", {})
        return fixture_summary(pool, idx), featured_next.get("detail", "")

    return "8강전 완료", "모든 8강 경기가 종료되었습니다."


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
    completed_matches = []

    if not error:
        completed_matches = [match for match in matches if match.get("completed")]

    featured = pool.get("featured", {})
    recent = featured.get("recent", {})
    latest_match = latest_completed_fixture_match(pool, completed_matches)
    next_summary, next_detail = next_fixture_match(pool, matches if not error else [])

    cols = st.columns(2)
    with cols[0]:
        render_match_card(
            "result",
            "가장 최근 경기 결과",
            match_summary(latest_match) if latest_match else recent.get("summary", "프랑스 2 - 0 모로코"),
            recent.get("detail", "득점: 음바페, 뎀벨레"),
        )
    with cols[1]:
        render_match_card(
            "",
            "다음 예정 경기",
            next_summary,
            next_detail,
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
            f'<div class="winner-box">{round_def["label"]} 승자: {", ".join(winners)} · {winner_reason(pool, round_id, top_score)}</div>',
            unsafe_allow_html=True,
        )
    else:
        if round_id == "qf":
            st.caption("8강 4경기 결과와 총 골수 결과가 모두 입력되면 승자가 표시됩니다.")
        else:
            st.caption("라운드 결과가 모두 입력되면 승자가 표시됩니다.")

    score_cells = "".join(
        f"<td><b>{participant_score(pool, participant, round_id)}</b></td>"
        for participant in participants
    )
    goal_cells = "".join(
        f"<td>{participant.get('tiebreaker_goals', '') if round_id == 'qf' else ''}</td>"
        for participant in participants
    )
    qf_total_goals = pool.get("result_total_goals", {}).get("qf")
    qf_total_goals_display = qf_total_goals if qf_total_goals not in [None, ""] else "대기"
    header_cells = "".join(
        f"<th>{participant['name']}{' 🏆' if participant['name'] in winners else ''}</th>"
        for participant in participants
    )

    html = f"""
    <table class="score-table">
      <tr><th>구분</th>{header_cells}</tr>
      <tr><td>적중 수</td>{score_cells}</tr>
      {"<tr><td>총 골수</td>" + goal_cells + "</tr>" if round_id == "qf" else ""}
      {"<tr><td>총 골수 결과</td><td colspan='" + str(len(participants)) + "'><b>" + str(qf_total_goals_display) + "</b></td></tr>" if round_id == "qf" else ""}
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
    st.subheader("누적 라운드 승리")
    participants = pool.get("participants", [])
    past_wins = pool.get("past_wins", {})
    round_win_counts = {participant["name"]: int(past_wins.get(participant["name"], 0)) for participant in participants}

    for round_id in ["r16", "qf", "champion"]:
        if not is_round_complete(pool, round_id):
            continue
        winners, _ = round_winners(pool, round_id)
        for winner in winners:
            round_win_counts[winner] = round_win_counts.get(winner, 0) + 1

    rows = []
    for participant in participants:
        rows.append(
            {
                "이름": participant["name"],
                "누적승": round_win_counts.get(participant["name"], 0),
                "비고": "32강 우승 이력 포함" if participant["name"] in past_wins else "",
            }
        )

    if not rows:
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.bar_chart(df.set_index("이름")[["누적승"]])


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

        pool.setdefault("result_total_goals", {})
        total_goal_input = st.text_input(
            "8강전 4경기 총 골수 결과",
            value=str(pool.get("result_total_goals", {}).get("qf") or ""),
            help="8강 4경기에서 나온 모든 골의 합계입니다. 8강 적중 수 동점일 때 이 값과 가장 가까운 사람이 승자입니다.",
        )
        pool["result_total_goals"]["qf"] = int(total_goal_input) if total_goal_input.strip().isdigit() else ""

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


st_autorefresh(interval=AUTO_REFRESH_MS, key="live_refresh")

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
pool = load_pool()
live_matches_for_overlay, live_error_for_overlay = fetch_live_matches()
if not live_error_for_overlay:
    pool = auto_apply_live_results(pool, live_matches_for_overlay)
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
