# 🌡️ fkai-eye — 不快指数 3D マップ

日本の**不快指数（Discomfort Index）**を地図上に3Dでリアルタイム可視化するインタラクティブWebアプリです。

## スクリーンショット

> Streamlit + Pydeck による 3D コラムマップ（モードA）と IDW 補間サーフェス（モードB）

## 不快指数の計算式

```
DI = 0.81 × T + 0.01 × U × (0.99 × T − 14.3) + 46.3
```

| DI | 感覚 |
|---|---|
| ≤ 60 | 不快でない |
| 60–65 | やや不快 |
| 65–70 | 不快 |
| 70–75 | かなり不快 |
| 75–80 | 非常に不快 |
| 80+ | 暑くてたまらない |

## 機能

- **モードA（離散表示）**: 47都道府県庁所在地の不快指数を3D柱で可視化
- **モードB（連続サーフェス）**: IDW空間補間で日本全土を滑らかな3Dヒートマップで表示
- **タイムラインアニメーション**: 24時間予報の変化をシークバー・再生ボタンで確認
- **クイックスナップ**: 全国・関東・九州・沖縄・北海道・近畿へワンクリック移動
- **リアルタイムデータ**: [Open-Meteo API](https://open-meteo.com/) からAPIキー不要で取得

## セットアップ

```bash
# uv がインストール済みの場合
uv run streamlit run app.py
```

## 技術スタック

| 役割 | ライブラリ |
|---|---|
| UIフレームワーク | [Streamlit](https://streamlit.io/) |
| 3D地図描画 | [Pydeck](https://deckgl.readthedocs.io/) |
| データ処理 | Pandas, NumPy |
| 空間補間 | SciPy (IDW) |
| 気象データ | [Open-Meteo API](https://open-meteo.com/) |
| パッケージ管理 | [uv](https://docs.astral.sh/uv/) |

## ディレクトリ構成

```
fkai-eye/
├── app.py               # Streamlit メインアプリ
├── src/
│   ├── prefectures.py   # 都道府県座標データ・ビュー設定
│   ├── fetcher.py       # Open-Meteo API取得・不快指数計算
│   └── interpolation.py # IDW空間補間・カラーマッピング
├── pyproject.toml
└── README.md
```
