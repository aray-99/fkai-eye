"""
🌡️ 不快指数マップ – Japan Discomfort Index 3D Visualizer
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
# Imports
# ---------------------------------------------------------------------------
import logging
import os
import sys
import time

import pydeck as pdk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from prefectures import PREFECTURES, REGION_VIEWS
from fetcher import (
    fetch_all_prefectures,
    fetch_all_parallel,
    get_mock_data,
)
from interpolation import (
    interpolate_discomfort_smooth,
    create_tin_wireframe,
    get_di_color,
    di_to_normalized,  # noqa: F401 – available for downstream use
)
from municipalities import get_all_municipalities

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
_DEFAULTS: dict = {
    "cam_lat":     37.0,
    "cam_lon":     137.0,
    "cam_zoom":    4.5,
    "playing":     False,
    "current_hour": 0,
    "anim_speed":  "普通 (0.8s)",
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def load_live_data(use_municipalities: bool) -> tuple:
    """Live data from Open-Meteo (cached 30 min).  Falls back to mock on error."""
    if use_municipalities:
        stations = get_all_municipalities()
        if not stations:
            stations = PREFECTURES
        try:
            df = fetch_all_parallel(stations, max_workers=15)
            return df, False
        except Exception as exc:
            logging.error("Parallel fetch failed: %s", exc)
            return get_mock_data(stations), True
    else:
        try:
            df = fetch_all_prefectures(PREFECTURES)
            return df, False
        except Exception as exc:
            logging.error("Sequential fetch failed: %s", exc)
            return get_mock_data(PREFECTURES), True


@st.cache_data(show_spinner=False)
def load_mock_data(use_municipalities: bool) -> tuple:
    """Deterministic mock data (no network)."""
    if use_municipalities:
        stations = get_all_municipalities()
        if not stations:
            stations = PREFECTURES
    else:
        stations = PREFECTURES
    return get_mock_data(stations), True


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
        "source", ["🌐 ライブAPI (Open-Meteo)", "🔧 モックデータ"],
        label_visibility="collapsed",
    )

    # ── Data resolution ───────────────────────────────────────────────────────
    st.markdown("### 📊 観測点数")
    data_res = st.radio(
        "resolution",
        ["標準 (47都道府県庁)", "高精度 (全市町村)"],
        label_visibility="collapsed",
    )
    if data_res.startswith("高精度"):
        st.caption("💡 初回は Natural Earth からデータをダウンロードし、"
                   "並列APIフェッチを行います（初回のみ 1〜2 分）。")

    st.markdown("---")

    # ── Display mode ──────────────────────────────────────────────────────────
    st.markdown("### 🗺️ 表示モード")
    display_mode = st.radio(
        "mode",
        ["A: 離散表示（3D 柱）", "B: TIN メッシュ（補間サーフェス）"],
        label_visibility="collapsed",
    )
    if display_mode.startswith("A"):
        st.caption("各観測点の不快指数を 3D 柱の高さと色で表示します。")
    else:
        st.caption("Delaunay 三角分割ワイヤーフレーム ＋ CloughTocher C1 三次補間による"
                   "滑らかな 3D サーフェスを日本列島の形に沿って描画します。")

    st.markdown("---")

    # ── Timeline ──────────────────────────────────────────────────────────────
    st.markdown("### ⏱️ タイムライン")

    if not st.session_state.playing:
        st.slider(
            "時刻", min_value=0, max_value=23,
            format="%d時", key="current_hour",
        )
    else:
        st.info(f"▶️ 再生中: {st.session_state.current_hour:02d}:00")

    btn1, btn2 = st.columns(2)
    with btn1:
        if st.button("▶️ 再生", disabled=st.session_state.playing,
                     use_container_width=True):
            st.session_state.playing = True
            st.rerun()
    with btn2:
        if st.button("⏹️ 停止", use_container_width=True):
            st.session_state.playing = False

    if not st.session_state.playing:
        st.selectbox(
            "アニメーション速度",
            ["遅い (1.5s)", "普通 (0.8s)", "速い (0.3s)"],
            key="anim_speed",
        )

    st.markdown("---")

    # ── Quick snap ────────────────────────────────────────────────────────────
    st.markdown("### 📍 クイックスナップ")
    _snap_regions = ["全国", "関東", "九州", "沖縄", "北海道", "近畿"]
    _snap_cols = st.columns(3)
    for _i, _region in enumerate(_snap_regions):
        with _snap_cols[_i % 3]:
            if st.button(_region, key=f"snap_{_region}", use_container_width=True):
                _vs = REGION_VIEWS[_region]
                st.session_state.cam_lat  = _vs["latitude"]
                st.session_state.cam_lon  = _vs["longitude"]
                st.session_state.cam_zoom = _vs["zoom"]

    # ── Mouse / keyboard hint ─────────────────────────────────────────────────
    st.caption(
        "🖱️ **右ドラッグ** または **Ctrl＋ドラッグ** で 3D 視点変更 ／ "
        "**スクロール** でズーム"
    )

    st.markdown("---")

    # ── Color legend ──────────────────────────────────────────────────────────
    st.markdown("### 🎨 DI カラー凡例")
    for _emoji, _rng, _lbl in [
        ("🔵", "≤ 60",  "不快でない"),
        ("🟢", "60–65", "やや不快"),
        ("🟡", "65–70", "不快"),
        ("🟠", "70–75", "かなり不快"),
        ("🔴", "75–80", "非常に不快"),
        ("🟣", "80＋",  "暑くてたまらない"),
    ]:
        st.markdown(f"{_emoji} **{_rng}** &nbsp; {_lbl}")

    st.markdown("---")
    st.markdown("**DI 計算式**")
    st.latex(r"DI = 0.81T + 0.01U(0.99T - 14.3) + 46.3")
    st.caption("T: 気温 (°C)　U: 相対湿度 (%)")


# ---------------------------------------------------------------------------
# Main area – header
# ---------------------------------------------------------------------------
st.title("🌡️ 日本の不快指数 リアルタイム 3D マップ")
st.caption("Open-Meteo API | CloughTocher 補間 | Natural Earth 海岸線クリップ | Pydeck + Streamlit")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
use_muni = data_res.startswith("高精度")

with st.spinner("データ取得中…"):
    if data_source.startswith("🌐"):
        df, is_mock = load_live_data(use_muni)
    else:
        df, is_mock = load_mock_data(use_muni)

n_stations = len(df) // 24  # 24 hours per station

if is_mock:
    st.warning("⚠️ モックデータを表示中（ネットワーク未接続またはモックモード選択）")
else:
    st.success(f"✅ ライブデータ取得完了 — **{n_stations} 地点** / 24 時間")

# ---------------------------------------------------------------------------
# Filter to selected hour
# ---------------------------------------------------------------------------
df_hour = df[df["hour"] == st.session_state.current_hour].copy()

st.markdown(f"**表示時刻: {st.session_state.current_hour:02d}:00 JST**")

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
_max_di  = df_hour["discomfort_index"].max()
_min_di  = df_hour["discomfort_index"].min()
_avg_di  = df_hour["discomfort_index"].mean()
_hot_row = df_hour.loc[df_hour["discomfort_index"].idxmax()]

_m1, _m2, _m3, _m4 = st.columns(4)
_m1.metric("🔺 最高 DI",  f"{_max_di:.1f}")
_m2.metric("🔻 最低 DI",  f"{_min_di:.1f}")
_m3.metric("📊 平均 DI",  f"{_avg_di:.1f}")
_m4.metric("🏆 最も暑い", _hot_row["name"], f"DI {_hot_row['discomfort_index']:.1f}")

# ---------------------------------------------------------------------------
# ViewState (built from snap-button session state; pitch fixed at 45°)
# ---------------------------------------------------------------------------
view_state = pdk.ViewState(
    latitude  = st.session_state.cam_lat,
    longitude = st.session_state.cam_lon,
    zoom      = st.session_state.cam_zoom,
    pitch     = 45,
    bearing   = 0,
)

# ---------------------------------------------------------------------------
# Build pydeck layers
# ---------------------------------------------------------------------------
# Scale column radius by station density
_col_radius = (
    45_000 if n_stations <= 50 else
    20_000 if n_stations <= 200 else
    10_000
)

if display_mode.startswith("A"):
    # ── Mode A: discrete 3-D columns ─────────────────────────────────────────
    df_hour["elevation"] = ((df_hour["discomfort_index"] - 55) * 9_000).clip(lower=0)
    df_hour["color"]     = df_hour["discomfort_index"].apply(
        lambda x: list(get_di_color(x))
    )

    layers = [
        pdk.Layer(
            "ColumnLayer",
            data=df_hour,
            get_position=["lon", "lat"],
            get_elevation="elevation",
            elevation_scale=1,
            radius=_col_radius,
            get_fill_color="color",
            pickable=True,
            auto_highlight=True,
            extruded=True,
            coverage=0.9,
        )
    ]
    tooltip = {
        "html": (
            "<b>{name}</b><br/>"
            "不快指数: <b>{discomfort_index}</b><br/>"
            "気温: {temperature}°C　湿度: {humidity}%"
        ),
        "style": {
            "backgroundColor": "rgba(0,0,0,0.78)",
            "color": "white",
            "fontSize": "13px",
            "borderRadius": "6px",
            "padding": "8px 10px",
        },
    }

else:
    # ── Mode B: TIN wireframe + CloughTocher smooth surface ───────────────────
    with st.spinner("TIN メッシュ生成中（CloughTocher2D 補間）…"):
        df_grid  = interpolate_discomfort_smooth(df_hour, resolution=0.3)
        tin_edges = create_tin_wireframe(df_hour, elevation_scale=9_000)

    df_grid["elevation"] = ((df_grid["discomfort_index"] - 55) * 9_000).clip(lower=0)

    # Smooth interpolated surface (hexagonal columns tiling the Japan coastline)
    surface_layer = pdk.Layer(
        "ColumnLayer",
        data=df_grid,
        get_position=["lon", "lat"],
        get_elevation="elevation",
        elevation_scale=1,
        radius=20_000,          # ~0.3° at 35°N; slight overlap for full coverage
        get_fill_color=["color_r", "color_g", "color_b", "color_a"],
        extruded=True,
        disk_resolution=6,      # hexagonal cross-section → tighter packing
        pickable=False,
    )

    # Delaunay TIN wireframe drawn as 3-D lifted lines
    wireframe_layer = pdk.Layer(
        "LineLayer",
        data=tin_edges,
        get_source_position="source",   # [lon, lat, elevation]
        get_target_position="target",
        get_color=[255, 255, 255, 90],
        get_width=1_500,                # metres
        width_min_pixels=1,
        pickable=False,
    )

    # Station markers for hover tooltip
    marker_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_hour[
            ["name", "lat", "lon", "discomfort_index", "temperature", "humidity"]
        ].copy(),
        get_position=["lon", "lat"],
        radius_min_pixels=3,
        radius_max_pixels=9,
        get_fill_color=[255, 255, 255, 220],
        stroked=True,
        get_line_color=[30, 30, 30, 255],
        get_line_width=200,
        pickable=True,
        auto_highlight=True,
    )

    layers  = [surface_layer, wireframe_layer, marker_layer]
    tooltip = {
        "html": (
            "<b>{name}</b><br/>"
            "不快指数: <b>{discomfort_index}</b><br/>"
            "気温: {temperature}°C　湿度: {humidity}%"
        ),
        "style": {
            "backgroundColor": "rgba(0,0,0,0.78)",
            "color": "white",
            "fontSize": "13px",
            "borderRadius": "6px",
            "padding": "8px 10px",
        },
    }

# ---------------------------------------------------------------------------
# Render map
# ---------------------------------------------------------------------------
deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
)
st.pydeck_chart(deck, use_container_width=True, height=620)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    "<small>"
    "📡 気象データ: <a href='https://open-meteo.com/' target='_blank'>Open-Meteo</a> "
    "（APIキー不要）&nbsp;｜&nbsp;"
    "🗾 海岸線: <a href='https://www.naturalearthdata.com/' target='_blank'>"
    "Natural Earth</a> 50m&nbsp;｜&nbsp;"
    "🎨 青→緑→黄→橙→赤→紫 (DI 55–80)&nbsp;｜&nbsp;"
    "📐 DI = 0.81T + 0.01U(0.99T − 14.3) + 46.3"
    "</small>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Animation logic (runs after current frame is displayed)
# ---------------------------------------------------------------------------
if st.session_state.playing:
    _speed_map = {"遅い (1.5s)": 1.5, "普通 (0.8s)": 0.8, "速い (0.3s)": 0.3}
    _delay = _speed_map.get(
        st.session_state.get("anim_speed", "普通 (0.8s)"), 0.8
    )
    time.sleep(_delay)
    _next = (st.session_state.current_hour + 1) % 24
    st.session_state.current_hour = _next
    if _next == 0:
        st.session_state.playing = False  # stop after one full 24-h cycle
    st.rerun()
