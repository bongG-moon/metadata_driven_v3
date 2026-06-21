from __future__ import annotations

import html
import sys
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent

try:
    from .langflow_client import LangflowApiClient, LangflowSettings
    from .mock_api import MockApiClient
    from .ui_helpers import chat_dataframe_height, compact_json_html, display_table_frame, json_text, safe_markdown_text
except ImportError:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from web_app.langflow_client import LangflowApiClient, LangflowSettings
    from web_app.mock_api import MockApiClient
    from web_app.ui_helpers import chat_dataframe_height, compact_json_html, display_table_frame, json_text, safe_markdown_text


APP_TITLE = "Metadata Agent Console"
PAGE_QUERY = "질의/분석"
PAGE_AUTHORING = "Metadata 등록"
PAGE_LOOKUP = "Metadata 조회"
PAGE_VALIDATE = "등록 후 검증"
NAV_PAGES = [PAGE_QUERY, PAGE_AUTHORING, PAGE_LOOKUP, PAGE_VALIDATE]

AUTHORING_TYPES = {
    "domain": "Domain",
    "table_catalog": "Table catalog",
    "main_flow_filter": "Main flow filter",
}
AUTHORING_DESCRIPTIONS = {
    "domain": "업무 용어, 공정 그룹, 제품 조건, metric, join rule을 domain metadata로 변환하고 검토한 뒤 저장합니다.",
    "table_catalog": "dataset, source, query_template, 컬럼, filter mapping 정보를 table catalog metadata로 등록합니다.",
    "main_flow_filter": "날짜, 공정, MODE, 제품 속성처럼 여러 dataset에서 공통으로 쓰는 표준 의미 필터를 등록합니다.",
}
AUTHORING_EXAMPLE_PATHS = {
    "domain": REPO_ROOT / "langflow_components" / "domain_authoring_flow" / "raw_text_input_example.md",
    "table_catalog": REPO_ROOT / "langflow_components" / "table_catalog_authoring_flow" / "raw_text_input_example.md",
    "main_flow_filter": REPO_ROOT / "langflow_components" / "main_flow_filters_authoring_flow" / "raw_text_input_example.md",
}
ACTION_LABELS = {
    "ask": "먼저 확인",
    "merge": "기존 내용 보강",
    "replace": "기존 내용 교체",
    "skip": "저장하지 않음",
    "create_new": "새 key로 등록",
}
QUERY_EXAMPLES = [
    "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
    "현재 da에서 재공이 가장 많은 제품 알려줘",
    "이 제품에 할당된 장비 현황 알려줘",
    "오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘",
    "현재 조회 가능한 DATA LIST 알려줘",
    "production_today 조회 쿼리문 알려줘",
]
AUTHORING_EXAMPLES = {
    "domain": "W/B공정은 W/B1부터 W/B6까지야. 재공 수량은 WIP 컬럼을 합산해.",
    "table_catalog": "wip_today는 Oracle PNT_RPT에서 SELECT WORK_DT, OPER_NAME, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE}로 조회해. DATE는 WORK_DT에 매핑해.",
    "main_flow_filter": "날짜 조건은 DATE라는 기준 필터로 사용해줘. 오늘, 금일, 작업일은 WORK_DT 후보 컬럼과 연결해.",
}


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_style()
    ensure_state()
    settings = render_sidebar()
    if settings["page"] == PAGE_QUERY:
        render_query_page(settings)
    elif settings["page"] == PAGE_AUTHORING:
        render_authoring_page(settings)
    elif settings["page"] == PAGE_LOOKUP:
        render_lookup_page(settings)
    else:
        render_validation_page(settings)


def ensure_state() -> None:
    if "mock_api" not in st.session_state:
        st.session_state.mock_api = MockApiClient()
    if "langflow_api" not in st.session_state:
        st.session_state.langflow_api = LangflowApiClient()
    if "session_id" not in st.session_state:
        st.session_state.session_id = new_session_id()
    if "session_id_input" not in st.session_state:
        st.session_state.session_id_input = st.session_state.session_id
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "latest_state" not in st.session_state:
        st.session_state.latest_state = {}
    if "authoring_results" not in st.session_state:
        st.session_state.authoring_results = []


def new_session_id() -> str:
    return f"web-{uuid.uuid4().hex[:8]}"


def reset_conversation(session_id: str | None = None, keep_session: bool = False) -> None:
    if not keep_session:
        st.session_state.session_id = str(session_id or new_session_id()).strip() or new_session_id()
        st.session_state.session_id_input = st.session_state.session_id
    st.session_state.chat_messages = []
    st.session_state.latest_state = {}
    st.session_state.pop("pending_question", None)


def authoring_example_text(flow_key: str) -> str:
    path = AUTHORING_EXAMPLE_PATHS.get(flow_key)
    if path and path.exists():
        return path.read_text(encoding="utf-8").strip()
    return AUTHORING_EXAMPLES.get(flow_key, "")


def authoring_input_payload(raw_text: str, review_notes: str) -> str:
    raw = str(raw_text or "").strip()
    notes = str(review_notes or "").strip()
    if not notes:
        return raw
    return f"{raw}\n\n[추가 검수 지시]\n{notes}"


def latest_chat_applied_scope() -> dict[str, Any]:
    messages = st.session_state.get("chat_messages")
    if not isinstance(messages, list):
        return {}
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        result = message.get("result") if isinstance(message.get("result"), dict) else {}
        scope = result.get("applied_scope") if isinstance(result.get("applied_scope"), dict) else {}
        if scope:
            return scope
    return {}


def state_summary_for_sidebar(state: dict[str, Any] | None = None, applied_scope: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state if isinstance(state, dict) else st.session_state.get("latest_state", {})
    applied_scope = applied_scope if isinstance(applied_scope, dict) else latest_chat_applied_scope()
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    datasets = current_data.get("source_dataset_keys") or applied_scope.get("datasets") or []
    if not isinstance(datasets, list):
        datasets = [datasets]
    source_aliases = current_data.get("source_aliases") or applied_scope.get("source_aliases") or []
    if not isinstance(source_aliases, list):
        source_aliases = [source_aliases]
    columns = current_data.get("columns") if isinstance(current_data.get("columns"), list) else []
    row_count = current_data.get("row_count")
    preview_rows = current_data.get("preview_rows") or current_data.get("rows") or []
    if not isinstance(preview_rows, list):
        preview_rows = []
    product_summary = current_data.get("product_key_summary") if isinstance(current_data.get("product_key_summary"), dict) else {}
    row_count_value = int_or_zero(row_count) or len(preview_rows)
    return {
        "datasets": [str(item) for item in datasets if str(item or "").strip()],
        "source_aliases": [str(item) for item in source_aliases if str(item or "").strip()],
        "row_count": row_count_value,
        "preview_count": len(preview_rows),
        "columns": [str(column) for column in columns[:8]],
        "product_key_count": int_or_zero(product_summary.get("count") or product_summary.get("product_count")),
        "has_state": bool(current_data or applied_scope),
    }


def active_scope_sidebar_html(state: dict[str, Any] | None = None, applied_scope: dict[str, Any] | None = None) -> str:
    summary = state_summary_for_sidebar(state, applied_scope)
    state_label = "활성" if summary["has_state"] else "대기"
    panel_class = "active-scope-panel" if summary["has_state"] else "active-scope-panel empty"
    if summary["has_state"]:
        dataset_text = ", ".join(summary["datasets"][:3]) or "dataset 정보 없음"
        if len(summary["datasets"]) > 3:
            dataset_text += f" 외 {len(summary['datasets']) - 3}개"
        alias_text = ", ".join(summary["source_aliases"][:3])
        columns_text = ", ".join(summary["columns"][:6])
        body_html = (
            f'<div class="active-scope-datasets">{html.escape(dataset_text)}</div>'
            '<div class="active-scope-chip-list">'
            f'<div class="active-scope-chip"><div class="active-scope-chip-label">Rows</div><div class="active-scope-chip-value">{summary["row_count"]:,}</div></div>'
            f'<div class="active-scope-chip"><div class="active-scope-chip-label">Preview</div><div class="active-scope-chip-value">{summary["preview_count"]:,}</div></div>'
            f'<div class="active-scope-chip"><div class="active-scope-chip-label">Product keys</div><div class="active-scope-chip-value">{summary["product_key_count"]:,}</div></div>'
            "</div>"
        )
        if alias_text:
            body_html += f'<div class="active-scope-footer">Aliases: {html.escape(alias_text)}</div>'
        if columns_text:
            body_html += f'<div class="active-scope-footer">Columns: {html.escape(columns_text)}</div>'
    else:
        body_html = '<div class="active-scope-empty-text">질의가 실행되면 후속 질문에서 이어 쓸 데이터셋, row 수, preview 정보가 여기에 표시됩니다.</div>'
    return (
        f'<div class="{panel_class}">'
        '<div class="active-scope-header">'
        '<div><div class="active-scope-kicker">Session state</div><div class="active-scope-title">후속 질문 기준</div></div>'
        f'<span class="active-scope-state">{html.escape(state_label)}</span>'
        "</div>"
        f"{body_html}"
        "</div>"
    )


def render_sidebar_active_scope(slot: Any | None = None, state: dict[str, Any] | None = None, applied_scope: dict[str, Any] | None = None) -> None:
    target = slot if slot is not None else st.sidebar
    target.markdown(active_scope_sidebar_html(state, applied_scope), unsafe_allow_html=True)


def render_session_controls(api_settings: LangflowSettings) -> None:
    configured = api_settings.configured_summary()
    st.sidebar.markdown('<div class="sidebar-section-label">Session</div>', unsafe_allow_html=True)
    st.sidebar.text_input("Session ID", key="session_id_input", help="기존 MongoDB session state를 이어 보려면 같은 Session ID를 입력한 뒤 적용하세요.")
    apply_col, new_col = st.sidebar.columns(2)
    if apply_col.button("세션 적용", width="stretch"):
        reset_conversation(str(st.session_state.session_id_input or st.session_state.session_id), keep_session=False)
        st.rerun()
    if new_col.button("새 세션", width="stretch"):
        reset_conversation()
        st.rerun()
    if st.sidebar.button("현재 화면 state 초기화", width="stretch"):
        reset_conversation(keep_session=True)
        st.rerun()
    store_label = api_settings.session_state_collection if configured.get("session_state") else "disabled"
    st.sidebar.markdown(
        f"""
        <div class="config-list session-store-list">
          <div class="config-row">
            <div><div class="config-label">Session State Store</div><div class="config-env">WEB_SESSION_STORE / MONGODB_SESSION_STATE_COLLECTION</div></div>
            <span class="config-badge {'ok' if configured.get('session_state') else 'warn'}">{'MongoDB' if configured.get('session_state') else 'Off'}</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Collection</div><div class="config-env">{html.escape(str(store_label))}</div></div>
            <span class="config-value">state</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> dict[str, Any]:
    api_settings = LangflowSettings.from_env()
    if getattr(st.session_state.langflow_api, "settings", None) != api_settings:
        st.session_state.langflow_api = LangflowApiClient(api_settings)
    configured = api_settings.configured_summary()
    api_ready = configured["query"]
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
          <div class="sidebar-brand-row">
            <div class="sidebar-brand-mark">M2</div>
            <div>
              <div class="sidebar-brand-title">Metadata Agent</div>
              <div class="sidebar-brand-subtitle">Langflow-ready web console</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio("Navigation", NAV_PAGES, label_visibility="collapsed", key="nav_page")
    st.sidebar.markdown('<div class="sidebar-section-label">Runtime</div>', unsafe_allow_html=True)
    runtime_mode = st.sidebar.radio(
        "Runtime mode",
        ["Python mock", "Langflow API"],
        index=0,
        label_visibility="collapsed",
        key="runtime_mode",
    )
    st.sidebar.markdown(
        f"""
        <div class="config-list">
          <div class="config-row">
            <div><div class="config-label">Selected</div><div class="config-env">{html.escape(runtime_mode)}</div></div>
            <span class="config-badge {'ok' if runtime_mode == 'Python mock' or api_ready else 'warn'}">{'Ready' if runtime_mode == 'Langflow API' and api_ready else 'Mock' if runtime_mode == 'Python mock' else 'Missing'}</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Query APIs</div><div class="config-env">ROUTER_FLOW_ID + subflow IDs</div></div>
            <span class="config-badge {'ok' if configured['query'] else 'warn'}">{'set' if configured['query'] else 'empty'}</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Authoring APIs</div><div class="config-env">domain/table/filter</div></div>
            <span class="config-value">{sum(1 for key in ('domain', 'table_catalog', 'main_flow_filter') if configured.get(key))}/3</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Result store</div><div class="config-env">MONGODB_RESULT_COLLECTION</div></div>
            <span class="config-value">agent_v3_result_store</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if runtime_mode == "Langflow API" and not api_ready:
        st.sidebar.warning("Query Langflow API URL 또는 flow id가 없어 질의를 실행할 수 없습니다. env 설정 전에는 Python mock을 사용하세요.")
    render_session_controls(api_settings)
    active_scope_slot = st.sidebar.empty()
    render_sidebar_active_scope(active_scope_slot)
    developer_mode = st.sidebar.toggle("개발자 정보 보기", value=True)
    number_mode = st.sidebar.selectbox("숫자 표시", ["comma", "k"], format_func=lambda item: "1,000" if item == "comma" else "1.0K")
    return {
        "page": page,
        "developer_mode": developer_mode,
        "number_mode": number_mode,
        "runtime_mode": runtime_mode,
        "api_ready": api_ready,
        "api_settings": api_settings,
        "active_scope_slot": active_scope_slot,
    }


def render_query_page(settings: dict[str, Any]) -> None:
    render_topbar("질의/분석", st.session_state.session_id)
    if settings.get("runtime_mode") == "Langflow API":
        st.caption("Langflow Run API 응답을 현재 웹 표준 shape로 정규화해서 표시합니다.")
    else:
        st.caption("Python mock API가 reference runtime을 호출합니다. 후속 질문 state와 data_ref 동작까지 화면에서 확인할 수 있습니다.")

    example_cols = st.columns(len(QUERY_EXAMPLES))
    for index, question in enumerate(QUERY_EXAMPLES):
        if example_cols[index].button(f"예시 {index + 1}", key=f"query_example_{index}", width="stretch"):
            st.session_state.pending_question = question

    for index, message in enumerate(st.session_state.chat_messages):
        with st.chat_message(message["role"], avatar=":material/person:" if message["role"] == "user" else ":material/smart_toy:"):
            if message["role"] == "assistant":
                render_query_result(message["result"], settings, f"history_{index}")
            else:
                st.markdown(safe_markdown_text(message["content"]))

    pending = st.session_state.pop("pending_question", None)
    user_message = st.chat_input("제조 데이터 질문을 입력하세요")
    if pending and not user_message:
        user_message = pending
    if not user_message:
        return

    st.session_state.chat_messages.append({"role": "user", "content": user_message})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(safe_markdown_text(user_message))
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        with st.spinner("Langflow API 실행 중..." if settings.get("runtime_mode") == "Langflow API" else "Python mock API 실행 중..."):
            result = run_query_backend(user_message, settings)
            st.session_state.latest_state = result.get("state", {})
            render_sidebar_active_scope(settings.get("active_scope_slot"), st.session_state.latest_state, result.get("applied_scope"))
        render_query_result(result, settings, "latest")
    st.session_state.chat_messages.append({"role": "assistant", "content": result.get("answer_message", ""), "result": result})


def run_query_backend(user_message: str, settings: dict[str, Any]) -> dict[str, Any]:
    try:
        if settings.get("runtime_mode") == "Langflow API":
            return st.session_state.langflow_api.run_query(
                user_message,
                session_id=st.session_state.session_id,
                state=st.session_state.latest_state or None,
            )
        return st.session_state.mock_api.run_query(
            user_message,
            session_id=st.session_state.session_id,
            state=st.session_state.latest_state or None,
        )
    except Exception as exc:
        return {
            "status": "error",
            "success": False,
            "answer_message": f"실행 중 오류가 발생했습니다: {exc}",
            "data": {"columns": [], "rows": [], "row_count": 0, "data_ref": {}},
            "applied_scope": {},
            "intent_plan": {},
            "analysis": {"status": "error", "errors": [str(exc)]},
            "state": st.session_state.latest_state or {},
            "warnings": [],
            "errors": [str(exc)],
            "api_mode": settings.get("runtime_mode", "unknown"),
        }


def render_query_result(result: dict[str, Any], settings: dict[str, Any], key_prefix: str) -> None:
    st.markdown(safe_markdown_text(result.get("answer_message") or "응답 메시지가 없습니다."))
    is_metadata_qa = bool(result.get("direct_response_ready") or result.get("response_type") == "metadata_qa" or result.get("metadata_qa"))
    metadata_qa = result.get("metadata_qa") if isinstance(result.get("metadata_qa"), dict) else {}
    if is_metadata_qa:
        render_inline_status("Metadata QA", metadata_qa_label(metadata_qa), "success")
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    columns = data.get("columns") if isinstance(data.get("columns"), list) else []
    row_count = int(data.get("row_count") or len(rows) or 0)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Rows", f"{row_count:,}")
    metric_cols[1].metric("Preview", f"{len(rows):,}")
    metric_cols[2].metric("Datasets", f"{len((result.get('applied_scope') or {}).get('datasets') or []):,}")
    metric_cols[3].metric("Status", str(result.get("status") or "ok"))
    if rows:
        frame = pd.DataFrame(rows)
        if columns:
            ordered = [column for column in columns if column in frame.columns]
            frame = frame[ordered + [column for column in frame.columns if column not in ordered]]
        st.dataframe(
            display_table_frame(frame, settings.get("number_mode", "comma")),
            hide_index=True,
            width="stretch",
            height=chat_dataframe_height(row_count),
        )
    else:
        render_inline_status("결과", "표시할 row가 없습니다.", "warning")

    data_ref = data.get("data_ref") if isinstance(data.get("data_ref"), dict) else {}
    if data_ref:
        with st.expander("전체 row data_ref", expanded=False):
            render_compact_json(data_ref)
            if result.get("api_mode") == "python_mock" or settings.get("runtime_mode") == "Python mock":
                full_rows = st.session_state.mock_api.get_rows(data_ref)
                st.download_button(
                    "전체 row JSON 다운로드",
                    data=json_text(full_rows),
                    file_name=f"{data_ref.get('ref_id', 'rows')}.json",
                    mime="application/json",
                    key=f"{key_prefix}_download_rows",
                    width="stretch",
                )
            else:
                render_inline_status("전체 row", "Langflow API 모드에서는 backend가 이 data_ref로 MongoDB result store를 조회합니다.")
                st.download_button(
                    "data_ref JSON 다운로드",
                    data=json_text(data_ref),
                    file_name=f"{data_ref.get('ref_id', 'data_ref')}.json",
                    mime="application/json",
                    key=f"{key_prefix}_download_ref",
                    width="stretch",
                )
    if is_metadata_qa:
        tabs = st.tabs(["Metadata QA", "적용 Scope", "Intent", "Raw"])
        with tabs[0]:
            render_compact_json(
                {
                    "metadata_qa": metadata_qa,
                    "metadata_route": result.get("metadata_route") or {},
                    "analysis": {key: value for key, value in (result.get("analysis") or {}).items() if key != "rows"},
                },
                max_height=360,
            )
        with tabs[1]:
            render_compact_json(result.get("applied_scope") or {})
        with tabs[2]:
            render_compact_json(result.get("intent_plan") or result.get("intent") or {})
        with tabs[3]:
            render_raw_result(result, settings)
    else:
        tabs = st.tabs(["적용 Scope", "Intent", "Pandas", "Raw"])
        with tabs[0]:
            render_compact_json(result.get("applied_scope") or {})
        with tabs[1]:
            render_compact_json(result.get("intent_plan") or result.get("intent") or {})
        with tabs[2]:
            analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
            code = analysis.get("analysis_code") or (analysis.get("pandas_code_json") or {}).get("code", "")
            if code:
                st.code(str(code), language="python")
            render_compact_json({key: value for key, value in analysis.items() if key not in {"rows", "analysis_code", "pandas_code_json"}})
        with tabs[3]:
            render_raw_result(result, settings)


def metadata_qa_label(metadata_qa: dict[str, Any]) -> str:
    action = str(metadata_qa.get("metadata_action") or "direct_answer")
    target = metadata_qa.get("target_dataset") or metadata_qa.get("target_family") or metadata_qa.get("target_term")
    if target:
        return f"{action} · {target}"
    return action


def render_raw_result(result: dict[str, Any], settings: dict[str, Any]) -> None:
    if settings.get("developer_mode"):
        render_compact_json(result, max_height=520)
    else:
        render_inline_status("개발자 정보", "사이드바에서 개발자 정보 보기를 켜면 Raw payload를 볼 수 있습니다.")


def render_authoring_page(settings: dict[str, Any]) -> None:
    render_topbar("Metadata 등록", st.session_state.session_id)
    flow_key = st.segmented_control("등록 유형", list(AUTHORING_TYPES), format_func=lambda key: AUTHORING_TYPES[key], default="domain")
    st.markdown(f"#### {AUTHORING_TYPES[flow_key]} 등록")
    st.caption(AUTHORING_DESCRIPTIONS.get(flow_key, ""))
    with st.expander("입력 예시 보기", expanded=False):
        st.code(authoring_example_text(flow_key), language="text")
        if st.button("예시 입력하기", key=f"load_authoring_example_{flow_key}"):
            st.session_state[f"authoring_text_{flow_key}"] = authoring_example_text(flow_key)
            st.rerun()
    action = st.selectbox("저장 방식", list(ACTION_LABELS), format_func=lambda key: ACTION_LABELS[key], index=0)
    st.session_state.setdefault(f"authoring_text_{flow_key}", "")
    text = st.text_area(
        "자연어 설명",
        key=f"authoring_text_{flow_key}",
        height=300,
        placeholder=f"예시)\n{authoring_example_text(flow_key)}",
    )
    review_notes = st.text_area(
        "추가 검수 지시",
        key=f"authoring_review_notes_{flow_key}",
        height=88,
        placeholder="예: 기존 항목과 충돌하면 merge 대신 보완 요청으로 돌려줘.",
    )
    run_col, clear_col = st.columns([1, 4])
    run_clicked = run_col.button("Langflow 실행" if settings.get("runtime_mode") == "Langflow API" else "Mock 실행", type="primary", width="stretch")
    if clear_col.button("결과 지우기", width="stretch"):
        st.session_state.authoring_results = []
        st.rerun()
    if run_clicked:
        if not str(text or "").strip():
            render_inline_status("입력", "등록할 자연어 설명을 입력해 주세요.", "warning")
        else:
            payload_text = authoring_input_payload(text, review_notes)
            with st.spinner("Langflow authoring API 실행 중..." if settings.get("runtime_mode") == "Langflow API" else "Python mock authoring 실행 중..."):
                result = run_authoring_backend(flow_key, payload_text, action, settings)
            result["flow_type"] = result.get("flow_type") or flow_key
            st.session_state[f"authoring_result_{flow_key}"] = result
            st.session_state.authoring_results.insert(0, result)
    if not st.session_state.authoring_results:
        render_inline_status("대기", "실행하면 정제 텍스트, 생성 item, 검토, 저장 결과가 표시됩니다.")
        return
    for index, result in enumerate(st.session_state.authoring_results[:5]):
        with st.container(border=False):
            render_authoring_result(result, f"authoring_{index}")


def run_authoring_backend(flow_key: str, text: str, action: str, settings: dict[str, Any]) -> dict[str, Any]:
    try:
        if settings.get("runtime_mode") == "Langflow API":
            return st.session_state.langflow_api.run_authoring(flow_key, text, action, st.session_state.session_id)
        return st.session_state.mock_api.run_authoring(flow_key, text, action, st.session_state.session_id)
    except Exception as exc:
        return {
            "status": "error",
            "ui_status": "error",
            "message": f"실행 중 오류가 발생했습니다: {exc}",
            "metadata_type": flow_key,
            "items": [],
            "existing_matches": [],
            "conflict_warnings": [],
            "review": {},
            "write_result": {"status": "error", "errors": [str(exc)]},
            "trace": {"raw_text": text, "duplicate_decision": {"action": action}},
            "errors": [str(exc)],
            "warnings": [],
            "api_mode": settings.get("runtime_mode", "unknown"),
        }


def authoring_status_label(status: Any) -> str:
    labels = {
        "saved": "저장 완료",
        "ok": "완료",
        "processed": "처리 완료",
        "needs_more_input": "추가 정보 필요",
        "duplicate_choice_required": "중복 처리 선택 필요",
        "warning": "확인 필요",
        "skipped": "저장 안 함",
        "error": "오류",
        "success": "완료",
        "ready_to_save": "저장 가능",
        "needs_supplement": "보완 필요",
    }
    return labels.get(str(status or "").strip(), str(status or "상태 없음"))


def authoring_status_tone(status: Any) -> str:
    text = str(status or "").strip()
    if text in {"saved", "ok", "success", "ready_to_save", "processed"}:
        return "success"
    if text in {"error", "failed"}:
        return "error"
    return "warning"


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def authoring_saved(result: dict[str, Any]) -> bool:
    write_result = result.get("write_result") if isinstance(result.get("write_result"), dict) else {}
    return bool(
        result.get("ui_status") == "saved"
        or write_result.get("success")
        or write_result.get("saved")
        or int_or_zero(write_result.get("saved_count")) > 0
    )


def authoring_ready_to_save(result: dict[str, Any]) -> bool:
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    if "ready_to_save" in review:
        return bool(review.get("ready_to_save"))
    return str(result.get("ui_status") or result.get("status") or "").strip() in {"saved", "ok", "ready_to_save"}


def authoring_needs_supplement(result: dict[str, Any]) -> bool:
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    return bool(review.get("needs_supplement") or review.get("supplement_requests") or result.get("ui_status") == "needs_more_input")


def authoring_item_summary_frame(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        rows.append(
            {
                "유형": item.get("section") or item.get("metadata_type") or item.get("type") or "",
                "키": item.get("key") or item.get("dataset_key") or item.get("filter_key") or "",
                "상태": item.get("status", ""),
                "표시명": payload.get("display_name") or item.get("display_name") or "",
                "source": (payload.get("source_config") or {}).get("source_type") if isinstance(payload.get("source_config"), dict) else payload.get("source_type", ""),
            }
        )
    return pd.DataFrame(rows)


def authoring_trace_stages(result: dict[str, Any]) -> list[dict[str, Any]]:
    trace = result.get("trace")
    if isinstance(trace, list):
        return [dict(stage) for stage in trace if isinstance(stage, dict)]
    trace_dict = trace if isinstance(trace, dict) else {}
    stages = [dict(stage) for stage in trace_dict.get("stages", []) if isinstance(stage, dict)]
    if stages:
        return stages
    raw_text = trace_dict.get("raw_text") or result.get("raw_text")
    refined_text = trace_dict.get("refined_text") or result.get("refined_text")
    duplicate_decision = trace_dict.get("duplicate_decision") if isinstance(trace_dict.get("duplicate_decision"), dict) else {}
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    write_result = result.get("write_result") if isinstance(result.get("write_result"), dict) else {}
    items = result.get("items") if isinstance(result.get("items"), list) else []
    built: list[dict[str, Any]] = []
    if raw_text:
        built.append({"stage": "input", "label": "사용자 입력", "status": "success", "raw_text": raw_text})
    if refined_text:
        built.append({"stage": "refinement", "label": "텍스트 정제", "status": "success", "refined_text": refined_text})
    if items:
        built.append({"stage": "normalization", "label": "Metadata item 생성", "status": "success", "items": items})
    if duplicate_decision:
        status = "warning" if duplicate_decision.get("requires_user_choice") else "success"
        built.append({"stage": "duplicate", "label": "중복 처리 판단", "status": status, "duplicate_decision": duplicate_decision})
    if review:
        status = "success" if review.get("ready_to_save") else "warning"
        built.append(
            {
                "stage": "review",
                "label": "검토",
                "status": status,
                "supplement_requests": review.get("supplement_requests"),
                "item_reviews": review.get("item_reviews"),
                "review": review,
            }
        )
    if write_result:
        status = "success" if authoring_saved(result) else str(write_result.get("status") or "warning")
        built.append({"stage": "write", "label": "저장", "status": status, "write_result": write_result})
    return built


def render_authoring_stage(stage: dict[str, Any], index: int, key_prefix: str) -> None:
    label = str(stage.get("label") or stage.get("stage") or f"Step {index}").strip()
    status = str(stage.get("status") or "").strip()
    expanded = status in {"warning", "error"} or stage.get("stage") in {"refinement", "review", "write"}
    with st.expander(f"{index}. {label} · {authoring_status_label(status)}", expanded=expanded):
        summary = str(stage.get("summary") or "").strip()
        if summary:
            st.markdown(safe_markdown_text(summary))
        if stage.get("raw_text"):
            st.text_area("사용자 입력 값", value=str(stage.get("raw_text") or ""), height=150, disabled=True, key=f"{key_prefix}_authoring_stage_{index}_raw")
        if stage.get("refined_text"):
            st.text_area("변환 텍스트", value=str(stage.get("refined_text") or ""), height=180, disabled=True, key=f"{key_prefix}_authoring_stage_{index}_refined")
        for key, title in (
            ("items", "생성 항목"),
            ("supplement_requests", "보완 요청"),
            ("item_reviews", "항목별 검토"),
            ("duplicate_decision", "중복 처리 판단"),
            ("write_result", "저장 결과"),
            ("review", "검토 원본"),
            ("errors", "오류"),
            ("warnings", "경고"),
        ):
            value = stage.get(key)
            if value:
                st.markdown(f"#### {title}")
                if key == "items" and isinstance(value, list):
                    st.dataframe(authoring_item_summary_frame([item for item in value if isinstance(item, dict)]), hide_index=True, width="stretch")
                render_compact_json(value, max_height=240)


def render_authoring_result(result: dict[str, Any], key_prefix: str) -> None:
    ui_status = result.get("ui_status") or result.get("status")
    render_inline_status(authoring_status_label(ui_status), result.get("message", ""), authoring_status_tone(ui_status))
    items = result.get("items") if isinstance(result.get("items"), list) else []
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    write_result = result.get("write_result") if isinstance(result.get("write_result"), dict) else {}
    summary_cols = st.columns(4)
    summary_cols[0].metric("Items", f"{len(items):,}")
    summary_cols[1].metric("Ready", "Yes" if authoring_ready_to_save(result) else "No")
    summary_cols[2].metric("Supplement", "Yes" if authoring_needs_supplement(result) else "No")
    summary_cols[3].metric("Saved", "Yes" if authoring_saved(result) else "No")
    tabs = st.tabs(["처리 과정", "생성 항목", "보완/중복", "저장 결과", "Raw JSON"])
    with tabs[0]:
        stages = authoring_trace_stages(result)
        if not stages:
            render_inline_status("처리 과정", "trace가 응답에 포함되어 있지 않습니다.", "warning")
        for index, stage in enumerate(stages, start=1):
            render_authoring_stage(stage, index, key_prefix)
    with tabs[1]:
        if items:
            st.dataframe(authoring_item_summary_frame([item for item in items if isinstance(item, dict)]), hide_index=True, width="stretch")
            render_compact_json(items, max_height=360)
        else:
            render_inline_status("items", "생성된 item이 없습니다.", "warning")
    with tabs[2]:
        render_detail_list("부족한 정보", review.get("supplement_requests") or [])
        render_detail_list("항목별 검토", review.get("item_reviews") or [])
        render_detail_list("비슷한 기존 정보", result.get("existing_matches") or [])
        render_detail_list("경고", result.get("conflict_warnings") or [])
        if result.get("pending_authoring_id"):
            st.markdown("#### Pending authoring id")
            st.code(str(result["pending_authoring_id"]))
    with tabs[3]:
        if write_result:
            render_compact_json(write_result, max_height=360)
        else:
            render_inline_status("저장 결과", "MongoDB writer 결과가 응답에 포함되어 있지 않습니다.", "warning")
    with tabs[4]:
        render_compact_json(result.get("api_response") or result, max_height=560)
        st.download_button(
            "Authoring 결과 JSON 다운로드",
            data=json_text(result.get("api_response") or result),
            file_name=f"metadata_authoring_{key_prefix}.json",
            mime="application/json",
            key=f"{key_prefix}_download_authoring_result",
            width="stretch",
        )


def render_lookup_page(settings: dict[str, Any]) -> None:
    render_topbar("Metadata 조회", st.session_state.session_id)
    flow_key = st.segmented_control("Metadata type", list(AUTHORING_TYPES), format_func=lambda key: AUTHORING_TYPES[key], default="domain", key="lookup_type")
    keyword = st.text_input("검색어", placeholder="key, alias, source type 검색")
    rows = st.session_state.mock_api.list_metadata(flow_key)
    if keyword:
        needle = keyword.lower()
        rows = [row for row in rows if needle in json_text(row).lower()]
    st.caption(f"{len(rows):,}개 metadata item")
    if rows:
        frame = pd.DataFrame([lookup_row(row, flow_key) for row in rows])
        st.dataframe(frame, hide_index=True, width="stretch", height=chat_dataframe_height(len(frame), 520))
        selected = st.selectbox("상세 보기", [lookup_label(row, flow_key) for row in rows])
        selected_row = rows[[lookup_label(row, flow_key) for row in rows].index(selected)]
        render_compact_json(selected_row, max_height=460)
    else:
        render_inline_status("검색", "조건에 맞는 metadata가 없습니다.", "warning")


def render_validation_page(settings: dict[str, Any]) -> None:
    render_topbar("등록 후 검증", st.session_state.session_id)
    questions = st.session_state.mock_api.validation_questions()
    labels = [f"{item['id']} - {item['question']}" for item in questions]
    selected = st.selectbox("검증 질문", labels)
    item = questions[labels.index(selected)]
    st.text_area("질문", value=item["question"], height=90, key="validation_question")
    if st.button("Langflow 검증 실행" if settings.get("runtime_mode") == "Langflow API" else "Mock 검증 실행", type="primary"):
        validation = run_validation_backend(st.session_state.validation_question, item.get("expected_datasets"), settings)
        st.session_state.validation_result = validation
    validation = st.session_state.get("validation_result")
    if not validation:
        render_inline_status("대기", "검증을 실행하면 기대 dataset과 실제 적용 결과를 비교합니다.")
        return
    tone = "success" if validation["passed"] else "error"
    render_inline_status("검증 결과", "통과" if validation["passed"] else "확인 필요", tone)
    cols = st.columns(2)
    cols[0].markdown("#### 기대 dataset")
    cols[0].write(validation["expected_datasets"])
    cols[1].markdown("#### 실제 dataset")
    cols[1].write(validation["actual_datasets"])
    render_query_result(validation["result"], settings, "validation")


def run_validation_backend(question: str, expected_datasets: list[str] | None, settings: dict[str, Any]) -> dict[str, Any]:
    if settings.get("runtime_mode") != "Langflow API":
        return st.session_state.mock_api.validate_question(
            question,
            expected_datasets=expected_datasets,
            session_id="validation-session",
        )
    result = run_query_backend(question, {"runtime_mode": "Langflow API", **settings})
    actual = set((result.get("applied_scope") or {}).get("datasets") or [])
    expected = set(expected_datasets or [])
    return {
        "passed": expected.issubset(actual) if expected else bool(result.get("answer_message")),
        "expected_datasets": sorted(expected),
        "actual_datasets": sorted(actual),
        "result": result,
    }


def render_topbar(title: str, session_id: str) -> None:
    safe_title = html.escape(title)
    safe_session = html.escape(str(session_id))
    st.markdown(
        f"""
        <div class="chat-topbar">
          <div class="chat-topbar-title">{safe_title}</div>
          <div class="session-strip">
            <div class="session-strip-label">Session ID</div>
            <div class="session-strip-value">{safe_session}</div>
          </div>
        </div>
        <div class="chat-topbar-spacer"></div>
        """,
        unsafe_allow_html=True,
    )


def render_inline_status(label: str, value: Any, tone: str = "info") -> None:
    safe_label = html.escape(str(label or ""))
    safe_value = html.escape(str(value or ""))
    st.markdown(f'<div class="inline-status inline-status-{tone}"><b>{safe_label}</b><span>{safe_value}</span></div>', unsafe_allow_html=True)


def render_compact_json(value: Any, max_height: int | None = None) -> None:
    style = f' style="max-height:{int(max_height)}px; overflow:auto;"' if max_height else ""
    st.html(f'<pre class="compact-json-block"{style}>{compact_json_html(value)}</pre>')


def render_detail_list(title: str, values: list[Any]) -> None:
    st.markdown(f"#### {title}")
    if not values:
        render_inline_status(title, "표시할 항목이 없습니다.")
        return
    for value in values:
        render_compact_json(value, max_height=180)


def flatten_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    return {
        "section": item.get("section", ""),
        "key": item.get("key") or item.get("dataset_key") or item.get("filter_key") or "",
        "status": item.get("status", ""),
        "display_name": payload.get("display_name", ""),
        "aliases": ", ".join(str(alias) for alias in payload.get("aliases", [])[:5]) if isinstance(payload.get("aliases"), list) else "",
    }


def lookup_row(row: dict[str, Any], flow_key: str) -> dict[str, Any]:
    if flow_key == "domain":
        return {
            "section": row.get("section"),
            "key": row.get("key"),
            "display_name": row.get("display_name"),
            "aliases": ", ".join(row.get("aliases", [])[:5]),
            "status": row.get("status"),
        }
    if flow_key == "table_catalog":
        return {
            "dataset_key": row.get("dataset_key"),
            "display_name": row.get("display_name"),
            "dataset_family": row.get("dataset_family"),
            "source_type": row.get("source_type"),
            "status": row.get("status"),
        }
    return {
        "filter_key": row.get("filter_key"),
        "display_name": row.get("display_name"),
        "semantic_role": row.get("semantic_role"),
        "column_candidates": ", ".join(row.get("column_candidates", [])[:4]),
        "status": row.get("status"),
    }


def lookup_label(row: dict[str, Any], flow_key: str) -> str:
    if flow_key == "domain":
        return f"{row.get('section')}/{row.get('key')}"
    if flow_key == "table_catalog":
        return str(row.get("dataset_key"))
    return str(row.get("filter_key"))


def inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --blue: #2563eb;
            --blue-dark: #1d4ed8;
            --ink: #101828;
            --muted: #667085;
            --line: #d7dde8;
            --surface: #ffffff;
            --soft: #f6f8fb;
            --green: #0f766e;
            --amber: #b45309;
            --red: #b42318;
        }
        .block-container { padding-top: 1.05rem; padding-bottom: 3rem; max-width: 1280px; }
        [data-testid="stAppViewContainer"] { background: #fbfcfe; color: var(--ink); }
        [data-testid="stSidebar"] { background: #f5f7fb; border-right: 1px solid var(--line); }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: 0.78rem; }
        .sidebar-brand { border-bottom: 1px solid var(--line); padding: 0.45rem 0 0.9rem; margin-bottom: 0.75rem; }
        .sidebar-brand-row { display: flex; align-items: center; gap: 0.7rem; }
        .sidebar-brand-mark {
            width: 2.15rem; height: 2.15rem; border-radius: 0.45rem;
            display: grid; place-items: center; color: #fff; background: var(--blue);
            font-weight: 800; font-size: 0.82rem;
        }
        .sidebar-brand-title { color: var(--ink); font-weight: 800; letter-spacing: 0; font-size: 0.98rem; }
        .sidebar-brand-subtitle { color: var(--muted); font-size: 0.72rem; margin-top: 0.06rem; }
        .sidebar-section-label { color: #475467; font-size: 0.68rem; font-weight: 800; text-transform: uppercase; margin: 1rem 0 0.35rem; }
        div[role="radiogroup"] label { min-height: 2rem; border-radius: 0.45rem; padding: 0.1rem 0.32rem; }
        div[role="radiogroup"] label:has(input:checked) { background: #eaf1ff; color: var(--blue-dark); }
        .config-list { display: grid; gap: 0.42rem; }
        .config-row {
            display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.6rem; align-items: center;
            border: 1px solid var(--line); background: var(--surface); border-radius: 0.45rem; padding: 0.55rem 0.62rem;
        }
        .config-label { color: #344054; font-size: 0.72rem; font-weight: 750; }
        .config-env { color: var(--muted); font-size: 0.64rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .config-badge { display: inline-flex; align-items: center; justify-content: center; min-height: 1.35rem; padding: 0 0.48rem; border-radius: 0.35rem; font-size: 0.66rem; font-weight: 750; }
        .config-badge.ok { background: #dff7ef; color: #047857; }
        .config-badge.warn { background: #fff7ed; color: #b45309; }
        .config-value { color: #475467; font-size: 0.68rem; }
        .session-store-list { margin-top: 0.42rem; }
        .active-scope-panel {
            border: 1px solid #bfd7ff; background: #eef5ff; border-radius: 0.45rem;
            padding: 0.62rem; margin: 0.7rem 0 0.95rem;
        }
        .active-scope-panel.empty { border-color: var(--line); background: var(--surface); }
        .active-scope-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.48rem; }
        .active-scope-kicker { color: var(--muted); font-size: 0.58rem; font-weight: 800; text-transform: uppercase; }
        .active-scope-title { color: var(--ink); font-size: 0.78rem; font-weight: 850; line-height: 1.2; }
        .active-scope-state {
            display: inline-flex; align-items: center; justify-content: center; min-height: 1.25rem;
            padding: 0 0.42rem; border-radius: 0.34rem; background: #dbeafe; color: #1d4ed8;
            font-size: 0.62rem; font-weight: 800;
        }
        .active-scope-panel.empty .active-scope-state { background: #f2f4f7; color: var(--muted); }
        .active-scope-datasets { color: #1e3a8a; font-size: 0.72rem; font-weight: 800; margin-bottom: 0.42rem; }
        .active-scope-empty-text, .active-scope-footer { color: var(--muted); font-size: 0.68rem; line-height: 1.45; }
        .active-scope-chip-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.34rem; margin-bottom: 0.42rem; }
        .active-scope-chip { border: 1px solid #d7e7ff; background: #ffffff; border-radius: 0.38rem; padding: 0.42rem; min-width: 0; }
        .active-scope-chip-label { color: var(--muted); font-size: 0.58rem; font-weight: 800; text-transform: uppercase; }
        .active-scope-chip-value { color: var(--ink); font-size: 0.72rem; font-weight: 850; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .chat-topbar {
            position: sticky; top: 0; z-index: 20; min-height: 2.7rem;
            display: flex; align-items: center; justify-content: space-between; gap: 1rem;
            background: rgba(251,252,254,0.96); backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--line); margin: -0.2rem 0 0.8rem; padding: 0.35rem 0;
        }
        .chat-topbar-title { color: var(--ink); font-size: 1rem; font-weight: 850; letter-spacing: 0; }
        .chat-topbar-spacer { height: 0.1rem; }
        .session-strip {
            display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.45rem;
            min-height: 2rem; border: 1px solid var(--line); background: var(--surface); border-radius: 0.45rem; padding: 0 0.58rem;
        }
        .session-strip-label { color: var(--muted); font-size: 0.62rem; font-weight: 800; text-transform: uppercase; }
        .session-strip-value { color: #344054; font-size: 0.72rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .inline-status {
            display: flex; align-items: center; gap: 0.48rem; border: 1px solid var(--line);
            border-radius: 0.45rem; padding: 0.52rem 0.62rem; margin: 0.35rem 0; background: var(--surface);
            font-size: 0.84rem; line-height: 1.45;
        }
        .inline-status b { font-size: 0.72rem; text-transform: uppercase; color: var(--muted); min-width: fit-content; }
        .inline-status-success { border-color: #a7f3d0; background: #ecfdf5; color: #065f46; }
        .inline-status-warning { border-color: #fde68a; background: #fffbeb; color: var(--amber); }
        .inline-status-error { border-color: #fecaca; background: #fff1f2; color: var(--red); }
        div[data-testid="stButton"] button, button[data-testid="stBaseButton-secondary"], button[data-testid="stBaseButton-primary"] {
            min-height: 2.05rem !important; border-radius: 0.45rem !important; font-size: 0.76rem !important; font-weight: 750 !important;
        }
        button[data-testid="stBaseButton-primary"] { background: var(--blue) !important; border-color: var(--blue) !important; color: #fff !important; }
        button[data-testid="stBaseButton-primary"]:hover { background: var(--blue-dark) !important; border-color: var(--blue-dark) !important; }
        div[data-testid="stTabs"] button[role="tab"] { font-size: 0.78rem; min-height: 2.1rem; }
        [data-testid="stChatInput"] textarea { min-height: 2.55rem !important; font-size: 0.86rem !important; }
        [data-testid*="ChatMessageAvatar"] { width: 1.95rem !important; height: 1.95rem !important; }
        div[data-testid="stCode"] code, div[data-testid="stCodeBlock"] code {
            font-size: 0.72rem !important; line-height: 1.38 !important;
        }
        .compact-json-block {
            background: #111827; color: #e5e7eb; border-radius: 0.45rem; padding: 0.72rem 0.82rem;
            font-size: 0.68rem !important; line-height: 1.42; white-space: pre-wrap; border: 1px solid #1f2937;
        }
        .compact-json-null { color: #9ca3af; }
        .compact-json-boolean { color: #5eead4; }
        div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 0.45rem; overflow: hidden; }
        h4 { font-size: 0.98rem !important; }
        @media (max-width: 780px) {
            .chat-topbar { align-items: flex-start; flex-direction: column; }
            .session-strip { width: 100%; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
