"""Replay-driven Streamlit console with explicit data provenance."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
REPLAY_DIR = ROOT / "results" / "replay"
SCENARIOS = {
    "Multi-turn Agent": "agent",
    "Bursty Serving": "burst",
    "Long-context QA": "long_context",
    "Video-like Trace Simulation": "video_like",
}


def load_events(name: str) -> list[dict]:
    path = REPLAY_DIR / f"{name}.jsonl"
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_summary() -> pd.DataFrame:
    return pd.read_csv(REPLAY_DIR / "policy_summary.csv")


def _provenance() -> None:
    st.caption(
        "REPLAY OF SIMULATION · Retrieve cost estimated from historical real Mooncake Store CSV "
        "(AutoDL RTX 4090) · Recompute cost estimated from V1 prefix model · "
        "No live Mooncake service or online KV mutation"
    )


def _history_table(events: list[dict], position: int) -> pd.DataFrame:
    latest = {}
    for event in events[: position + 1]:
        latest[event["kv_id"]] = event
        for transition in event["transitions"]:
            if transition["kv_id"] != event["kv_id"] and transition["kv_id"] in latest:
                latest[transition["kv_id"]] = dict(latest[transition["kv_id"]])
                latest[transition["kv_id"]]["state_after"] = transition["to"]
    rows = []
    for kv_id, event in latest.items():
        state = event["kv_state"]
        probability = state["reuse_probability"]
        rows.append({
            "KV ID": kv_id,
            "Prefix": state["prefix_id"],
            "Size (MiB)": state["size_mb"],
            "Reuse P": probability,
            "Frequency": state["frequency"],
            "Recency (requests)": position - event["timestamp"],
            "Retrieve (ms)": state["retrieve_cost_ms"],
            "Recompute (ms)": state["recompute_cost_ms"],
            "Value score": state["value_score"],
            "Tier": event["state_after"],
            "Action": event["actual_action"],
            "Status": "HOT" if probability >= 0.7 else ("WARM" if probability >= 0.4 else "COLD"),
        })
    return pd.DataFrame(rows).sort_values("KV ID") if rows else pd.DataFrame()


def _render_overview(events: list[dict], position: int) -> None:
    current = events[position]
    metrics = current["metrics"]
    left, right = st.columns([3, 1])
    with left:
        st.subheader("Decision Flow")
        flow = ["Incoming request", "KV profiler", "R³-KV", current["actual_action"], current["state_after"]]
        columns = st.columns(5)
        for column, label in zip(columns, flow):
            column.markdown(f"**{label}**")
        st.markdown(
            f"**{current['request_id']} · {current['kv_id']}**  |  "
            f"Reuse {current['decision'].get('reuse_probability', 0):.2f}  |  "
            f"Retrieve {current['kv_state']['retrieve_cost_ms']:.1f} ms  |  "
            f"Recompute {current['kv_state']['recompute_cost_ms']:.1f} ms"
        )
        st.info(current["decision"]["reason"])
        if current["transitions"]:
            st.caption("Lifecycle · " + " · ".join(
                f"{t['kv_id']} {t['from']} → {t['to']}" for t in current["transitions"]
            ))
    with right:
        st.subheader("Actions")
        counts = Counter(event["actual_action"] for event in events[: position + 1])
        counts["PREFETCH"] += sum(bool(event["prefetch"]) for event in events[: position + 1])
        st.bar_chart(pd.Series(counts).sort_values(ascending=False), horizontal=True)

    st.subheader("Workload Feedback")
    series = pd.DataFrame([
        {"Request": e["timestamp"], "Hit rate": e["metrics"]["cache_hit_rate"],
         "Memory pressure": e["metrics"]["memory_pressure"]}
        for e in events[: position + 1]
    ]).set_index("Request")
    st.line_chart(series, height=210)
    series2 = pd.DataFrame([
        {"Request": e["timestamp"], "Estimated TTFT (ms)": e["metrics"]["estimated_ttft_ms"],
         "P95 retrieval (ms)": e["metrics"]["p95_retrieval_ms"]}
        for e in events[: position + 1]
    ]).set_index("Request")
    st.line_chart(series2, height=210)
    st.subheader("KV Lifecycle")
    recent_transitions = [
        {"Request": e["timestamp"], "KV": t["kv_id"], "From": t["from"], "To": t["to"], "Reason": t["reason"]}
        for e in events[: position + 1] for t in e["transitions"]
    ]
    if recent_transitions:
        st.dataframe(pd.DataFrame(recent_transitions[-12:]), width="stretch", hide_index=True)


def _render_explorer(events: list[dict], position: int) -> str | None:
    st.subheader("KV State Explorer")
    table = _history_table(events, position)
    if table.empty:
        st.info("No KV objects accessed yet.")
        return None
    state_filter = st.multiselect("Tier", sorted(table["Tier"].unique()), default=sorted(table["Tier"].unique()))
    status_filter = st.multiselect("Temperature", ["HOT", "WARM", "COLD"], default=["HOT", "WARM", "COLD"])
    filtered = table[table["Tier"].isin(state_filter) & table["Status"].isin(status_filter)]
    st.dataframe(filtered, width="stretch", hide_index=True)
    selected = st.selectbox("Inspect KV", table["KV ID"].tolist())
    if selected:
        st.dataframe(table[table["KV ID"] == selected], width="stretch", hide_index=True)
    return selected


def _render_explainer(events: list[dict], position: int, selected: str | None) -> None:
    st.subheader("R³-KV Decision Explainer")
    options = list(dict.fromkeys(e["kv_id"] for e in events[: position + 1]))
    if not options:
        return
    selected = st.selectbox("KV object", options, index=options.index(selected) if selected in options else len(options) - 1, key="explain_kv")
    event = next(e for e in reversed(events[: position + 1]) if e["kv_id"] == selected)
    decision = event["decision"]
    if not decision.get("components"):
        st.info("This event has no R³-KV score decomposition.")
        return
    a, b = st.columns([2, 1])
    with a:
        st.bar_chart(pd.Series(decision["components"]), horizontal=True, height=260)
    with b:
        st.metric("Final score", f"{decision['score']:.3f}")
        st.metric("Reuse probability", f"{decision['reuse_probability']:.2f}")
        st.metric("Expected saved cost", f"{decision['expected_saved_ms']:.1f} ms")
        st.metric("Value density", f"{decision['value_density_ms_per_mb']:.1f} ms/MiB")
    st.success(f"{decision['action']} · {decision['reason']}")
    st.caption("Inputs are normalized before scoring. This is a simulation decision, not an executed Mooncake action.")


def _render_adaptive(events: list[dict], position: int) -> None:
    st.subheader("Adaptive Weight Controller")
    subset = events[: position + 1]
    rows = [{"Request": e["timestamp"], **e["weights"]} for e in subset]
    weight_df = pd.DataFrame(rows).melt(id_vars="Request", var_name="Weight", value_name="Value")
    weight_chart = (
        alt.Chart(weight_df)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("Request:Q", scale=alt.Scale(domain=[0, len(events) - 1]), title="Request"),
            y=alt.Y("Value:Q", scale=alt.Scale(domain=[0, 0.5]), title="Weight"),
            color=alt.Color("Weight:N", scale=alt.Scale(
                domain=["reuse", "saving", "locality", "load", "size"],
                range=["#67D4C4", "#F4C95D", "#76A9FA", "#F17C73", "#B5D99C"],
            )),
            tooltip=["Request:Q", "Weight:N", alt.Tooltip("Value:Q", format=".3f")],
        )
        .properties(height=270)
    )
    st.altair_chart(weight_chart, width="stretch")
    log = [event for e in subset for event in e["adaptive_events"]]
    left, right = st.columns([2, 1])
    with left:
        st.markdown("**Feedback**")
        st.line_chart(pd.DataFrame([
            {"Request": e["timestamp"], "Memory pressure": e["metrics"]["memory_pressure"],
             "Hit rate": e["metrics"]["cache_hit_rate"]} for e in subset
        ]).set_index("Request"), height=220)
    with right:
        st.markdown("**Adaptive Event Log**")
        if not log:
            st.info("No trigger fired in this replay window.")
        for event in reversed(log[-8:]):
            changes = [
                f"{key} {event['old_weights'][key]:.2f} → {new:.2f}"
                for key, new in event["new_weights"].items()
                if abs(new - event["old_weights"][key]) > 1e-9
            ]
            st.markdown(
                f"**Request {int(event['timestamp'])}** · {event['trigger_metric']} "
                f"{event['trigger_value']:.2f}  \n{', '.join(changes)}  \n{event['reason']}"
            )
    if log:
        with st.expander("Inspect weight changes"):
            st.dataframe(pd.DataFrame(log), width="stretch", hide_index=True)


def _render_policy_lab(scenario_name: str) -> None:
    st.subheader("Policy Lab · Shared-Trace Simulation")
    st.caption("All six policies run on the same seeded request trace and cache capacity. V1 source selection is adapted to a common LRU admission model; these are not live serving benchmarks.")
    df = load_summary()
    df = df[df["scenario"] == scenario_name].copy()
    columns = [
        "policy", "cache_hit_rate", "avg_estimated_ttft_ms", "p95_estimated_ttft_ms",
        "p99_estimated_ttft_ms", "p95_retrieval_ms", "p99_retrieval_ms", "remote_traffic_mb", "hotspot_ratio",
        "recompute_volume", "saved_prefill_time_ms", "memory_occupancy_mb", "prefetch_hit_rate",
    ]
    st.dataframe(df[columns], width="stretch", hide_index=True)
    chart = df.set_index("policy")[["avg_estimated_ttft_ms", "p95_estimated_ttft_ms"]]
    st.bar_chart(chart, horizontal=True)
    st.caption("Lower estimated TTFT is better; increased remote traffic or recomputation can erase benefits. No result is labeled REAL MOONCAKE.")


def render() -> None:
    st.title("CachePilot 2.0")
    st.caption("Adaptive KV Cache Management and Decision System")
    _provenance()
    if not (REPLAY_DIR / "policy_summary.csv").exists():
        st.error("Replay files are missing. Run `python -m cachepilot.replay.generate_demo` from the repository root.")
        return

    scenario_name = st.sidebar.selectbox("Workload", list(SCENARIOS))
    scenario_key = SCENARIOS[scenario_name]
    if st.session_state.get("replay_scenario") != scenario_key:
        st.session_state.replay_scenario = scenario_key
        st.session_state.replay_position = 0
        st.session_state.replay_playing = False
    events = load_events(scenario_key)
    speed = st.sidebar.select_slider("Replay speed", options=[1, 2, 4], value=1, format_func=lambda value: f"×{value}")
    jump_to = st.sidebar.number_input("Jump to request", min_value=1, max_value=len(events), value=1, step=1)
    if st.sidebar.button("Jump"):
        st.session_state.replay_position = jump_to - 1
        st.session_state.replay_playing = False
    c1, c2, c3 = st.sidebar.columns(3)
    if c1.button("▶", help="Play replay"):
        st.session_state.replay_playing = True
    if c2.button("Ⅱ", help="Pause replay"):
        st.session_state.replay_playing = False
    if c3.button("↺", help="Reset replay"):
        st.session_state.replay_position = 0
        st.session_state.replay_playing = False
    st.sidebar.caption("REPLAY · Seeded simulation, not a live service")

    @st.fragment(run_every="1s" if st.session_state.replay_playing else None)
    def playback() -> None:
        if st.session_state.replay_playing:
            st.session_state.replay_position = min(len(events) - 1, st.session_state.replay_position + speed)
            if st.session_state.replay_position == len(events) - 1:
                st.session_state.replay_playing = False
        position = st.session_state.replay_position
        current = events[position]
        metrics = current["metrics"]
        st.progress((position + 1) / len(events), text=f"Replay {position + 1} / {len(events)} · {current['request_id']}")
        kpis = st.columns(4)
        kpis[0].metric("Workload", {"agent": "Agent", "burst": "Burst", "long_context": "QA", "video_like": "Video-like"}[scenario_key])
        kpis[1].metric("Active KV", metrics["active_kv_objects"])
        kpis[2].metric("Memory", f"{metrics['memory_pressure'] * 100:.0f}%")
        kpis[3].metric("Hit rate", f"{metrics['cache_hit_rate'] * 100:.1f}%")
        kpis = st.columns(4)
        kpis[0].metric("Est. TTFT", f"{metrics['estimated_ttft_ms']:.1f} ms")
        kpis[1].metric("Remote traffic", f"{metrics['remote_traffic_mb']:.1f} MiB")
        kpis[2].metric("R³-KV mode", "Adaptive")
        kpis[3].metric("Mooncake", "V1 archive")
        tabs = st.tabs(["Overview", "KV State Explorer", "R³-KV Decision", "Adaptive Controller", "Policy Lab"])
        with tabs[0]:
            _render_overview(events, position)
        with tabs[1]:
            selected = _render_explorer(events, position)
        with tabs[2]:
            _render_explainer(events, position, selected)
        with tabs[3]:
            _render_adaptive(events, position)
        with tabs[4]:
            _render_policy_lab(scenario_name)

    playback()
