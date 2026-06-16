"""
🌡️ 不快指数マップ – Japan Discomfort Index 3D Visualizer
Main Streamlit application entry-point.
"""

# ---------------------------------------------------------------------------
# Page config — MUST be the very first Streamlit call
# ---------------------------------------------------------------------------
import streamlit as st

st.set_page_config(
    page_title="不快指数マップ",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Standard library & third-party imports
# ---------------------------------------------------------------------------
import os
import sys
import time

import pydeck as pdk

# ---------------------------------------------------------------------------
# Path setup — insert src/ so we can import local modules
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ---------------------------------------------------------------------------
# Project module imports
# ---------------------------------------------------------------------------
from prefectures import PREFECTURES, REGION_VIEWS  # noqa: E402
from fetcher import fetch_all_prefectures, get_mock_data  # noqa: E402
from interpolation import (  # noqa: E402
    interpolate_discomfort_for_hour,
    get_di_color,
    di_to_normalized,  # available for future use
)


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "view_state" not in st.session_state:
    st.session_state.view_state = dict(REGION_VIEWS["全国"])
if "playing" not in st.session_state:
    st.session_state.playing = False
if "current_hour" not in st.session_state:
    st.session_state.current_hour = 0
if "anim_speed" not in st.session_state:
    st.session_state.anim_speed = "普通 (0.8s)"


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------
@st.cache_data(ttl=1800)
def load_live_data() -> tuple:
    """Fetch live weather data from Open-Meteo; fall back to mock on any error."""
    try:
        df = fetch_all_prefectures(PREFECTURES)
        return df, False
    except Exception:
        df = get_mock_data(PREFECTURES)
        return df, True


@st.cache_data
def load_mock_data() -> tuple:
    """Return deterministic mock weather data (no network calls)."""
    df = get_mock_data(PREFECTURES)
    return df, True


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("# 🌡️ 不快指数マップ")
    st.markdown("**Japan Discomfort Index 3D Visualizer**")
    st.markdown("---")

    # ── Data source ──────────────────────────────────────────────────────────
    st.markdown("### 📡 データソース")
    data_source = st.radio(
        "データソース選択",
        options=["🌐 ライブAPI (Open-Meteo)", "🔧 モックデータ"],
        label_visibility="collapsed",
    )
    st.markdown("---")

    # ── Display mode ─────────────────────────────────────────────────────────
    st.markdown("### 🗺️ 表示モード")
    display_mode = st.radio(
        "表示モード選択",
        options=["A: 離散表示（柱グラフ）", "B: 連続サーフェス（IDW補間）"],
        label_visibility="collapsed",
    )
    if display_mode.startswith("A"):
        st.caption("各都市の不快指数を3D柱で表示します。")
    else:
        st.caption("IDW補間で日本全土を滑らかなサーフェスで可視化します。")
    st.markdown("---")

    # ── Timeline ─────────────────────────────────────────────────────────────
    st.markdown("### ⏱️ タイムライン")

    if not st.session_state.playing:
        selected_hour = st.slider(
            "時刻",
            min_value=0,
            max_value=23,
            value=st.session_state.current_hour,
            format="%d時",
            key="hour_slider",
        )
        st.session_state.current_hour = selected_hour
    else:
        st.info(f"▶️ 再生中: {st.session_state.current_hour:02d}:00")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("▶️ 再生", disabled=st.session_state.playing, use_container_width=True):
            st.session_state.playing = True
            st.rerun()
    with btn_col2:
        if st.button("⏹️ 停止", use_container_width=True):
            st.session_state.playing = False

    if not st.session_state.playing:
        st.selectbox(
            "アニメーション速度",
            options=["遅い (1.5s)", "普通 (0.8s)", "速い (0.3s)"],
            index=["遅い (1.5s)", "普通 (0.8s)", "速い (0.3s)"].index(
                st.session_state.get("anim_speed", "普通 (0.8s)")
            ),
            key="anim_speed",
        )

    st.markdown("---")

    # ── Quick-snap region buttons ─────────────────────────────────────────────
    st.markdown("### 📍 クイックスナップ")
    snap_regions = ["全国", "関東", "九州", "沖縄", "北海道", "近畿"]
    snap_cols = st.columns(3)
    for idx, region in enumerate(snap_regions):
        col = snap_cols[idx % 3]
        with col:
            if st.button(region, use_container_width=True, key=f"snap_{region}"):
                st.session_state.view_state = dict(REGION_VIEWS[region])

    st.markdown("---")

    # ── DI color legend ───────────────────────────────────────────────────────
    st.markdown("### 🎨 DI カラー凡例")
    legend_items = [
        ("🔵", "≤ 60", "不快でない"),
        ("🟢", "60–65", "やや不快"),
        ("🟡", "65–70", "不快"),
        ("🟠", "70–75", "かなり不快"),
        ("🔴", "75–80", "非常に不快"),
        ("🟣", "80+",   "暑くてたまらない"),
    ]
    for emoji, di_range, label in legend_items:
        st.markdown(f"{emoji} **{di_range}** &nbsp; {label}")

    st.markdown("---")
    st.markdown("**DI 計算式**")
    st.latex(r"DI = 0.81T + 0.01U(0.99T - 14.3) + 46.3")
    st.caption("T: 気温 (°C)　U: 相対湿度 (%)")


# ---------------------------------------------------------------------------
# Main content — header
# ---------------------------------------------------------------------------
st.title("🌡️ 日本の不快指数 リアルタイム3Dマップ")
st.caption("Open-Meteo API | Powered by Pydeck + Streamlit")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
if data_source.startswith("🌐"):
    df, is_mock = load_live_data()
else:
    df, is_mock = load_mock_data()

# Data source status banner
if is_mock:
    st.warning("⚠️ モックデータを表示中です。ネットワークエラーが発生したか、モックモードが選択されています。")
else:
    st.success("✅ Open-Meteo API からライブデータを取得しました。")

# ---------------------------------------------------------------------------
# Filter for selected hour
# ---------------------------------------------------------------------------
df_hour = df[df["hour"] == st.session_state.current_hour].copy()

# Current time label
time_label = "N/A"
if not df_hour.empty and "time" in df_hour.columns:
    try:
        ts = df_hour["time"].iloc[0]
        time_label = f"{st.session_state.current_hour:02d}:00 JST"
    except Exception:
        time_label = f"{st.session_state.current_hour:02d}:00"

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
st.markdown(f"**🕐 表示時刻:** {time_label}")

if not df_hour.empty:
    max_di = df_hour["discomfort_index"].max()
    min_di = df_hour["discomfort_index"].min()
    avg_di = df_hour["discomfort_index"].mean()
    hottest_row = df_hour.loc[df_hour["discomfort_index"].idxmax()]
    hottest_name = hottest_row["name"]
    hottest_di = hottest_row["discomfort_index"]

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric(label="🔺 最高 DI", value=f"{max_di:.1f}")
    with metric_cols[1]:
        st.metric(label="🔻 最低 DI", value=f"{min_di:.1f}")
    with metric_cols[2]:
        st.metric(label="📊 平均 DI", value=f"{avg_di:.1f}")
    with metric_cols[3]:
        st.metric(
            label="🏆 最も暑い",
            value=hottest_name,
            delta=f"DI {hottest_di:.1f}",
        )

# ---------------------------------------------------------------------------
# Build pydeck layers
# ---------------------------------------------------------------------------
view_state = pdk.ViewState(**st.session_state.view_state)

if display_mode.startswith("A"):
    # ── Mode A: Discrete column chart ────────────────────────────────────────
    df_hour["elevation"] = ((df_hour["discomfort_index"] - 55) * 9000).clip(lower=0)
    df_hour["color"] = df_hour["discomfort_index"].apply(lambda x: list(get_di_color(x)))
    df_hour["tooltip_text"] = (
        df_hour["name"] + " / DI: " + df_hour["discomfort_index"].astype(str)
    )

    layer = pdk.Layer(
        "ColumnLayer",
        data=df_hour,
        get_position=["lon", "lat"],
        get_elevation="elevation",
        elevation_scale=1,
        radius=45000,
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
        extruded=True,
        coverage=0.9,
    )

    tooltip = {
        "html": (
            "<b>{name}</b><br/>"
            "不快指数: <b>{discomfort_index}</b><br/>"
            "気温: {temperature}°C<br/>"
            "湿度: {humidity}%"
        ),
        "style": {
            "backgroundColor": "rgba(0,0,0,0.75)",
            "color": "white",
            "fontSize": "13px",
            "borderRadius": "6px",
            "padding": "8px",
        },
    }

    layers = [layer]

else:
    # ── Mode B: Continuous interpolated surface ───────────────────────────────
    with st.spinner("補間中... (IDW interpolation)"):
        df_grid = interpolate_discomfort_for_hour(df_hour, resolution=0.5)
        df_grid["elevation"] = ((df_grid["discomfort_index"] - 55) * 6000).clip(lower=0)

    surface_layer = pdk.Layer(
        "ColumnLayer",
        data=df_grid,
        get_position=["lon", "lat"],
        get_elevation="elevation",
        elevation_scale=1,
        radius=30000,
        get_fill_color=["color_r", "color_g", "color_b", "color_a"],
        extruded=True,
        disk_resolution=6,  # hexagonal tiles for tight packing
        pickable=False,
    )

    # Prefecture markers on top for identification
    df_markers = df_hour[["name", "lat", "lon", "discomfort_index"]].copy()

    marker_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_markers,
        get_position=["lon", "lat"],
        radius_min_pixels=4,
        radius_max_pixels=12,
        get_fill_color=[255, 255, 255, 200],
        pickable=True,
        auto_highlight=True,
    )

    tooltip = {
        "html": (
            "<b>{name}</b><br/>"
            "不快指数: <b>{discomfort_index}</b>"
        ),
        "style": {
            "backgroundColor": "rgba(0,0,0,0.75)",
            "color": "white",
            "fontSize": "13px",
            "borderRadius": "6px",
            "padding": "8px",
        },
    }

    layers = [surface_layer, marker_layer]

# ---------------------------------------------------------------------------
# Render pydeck map
# ---------------------------------------------------------------------------
deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
)

st.pydeck_chart(deck, use_container_width=True, height=600)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    "<small>"
    "📡 データソース: <a href='https://open-meteo.com/' target='_blank'>Open-Meteo</a> "
    "（気温・湿度の予報データ）　|　"
    "🎨 カラースケール: 青（涼しい）→ 緑 → 黄 → 橙 → 赤 → 紫（酷暑）　|　"
    "📐 DI = 0.81T + 0.01U(0.99T − 14.3) + 46.3"
    "</small>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Animation logic — runs AFTER rendering so the current frame is displayed
# first before advancing to the next hour.
# ---------------------------------------------------------------------------
if st.session_state.playing:
    speed_map = {"遅い (1.5s)": 1.5, "普通 (0.8s)": 0.8, "速い (0.3s)": 0.3}
    delay = speed_map.get(st.session_state.get("anim_speed", "普通 (0.8s)"), 0.8)
    time.sleep(delay)
    next_hour = (st.session_state.current_hour + 1) % 24
    st.session_state.current_hour = next_hour
    if next_hour == 0:
        st.session_state.playing = False  # stop after one full 24-hour cycle
    st.rerun()
