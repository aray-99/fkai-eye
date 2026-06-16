"""Prefecture coordinate data and regional view configurations for Japan."""

from typing import TypedDict


class Prefecture(TypedDict):
    name: str
    name_en: str
    lat: float
    lon: float
    region: str


class ViewState(TypedDict):
    latitude: float
    longitude: float
    zoom: float
    pitch: float
    bearing: float


PREFECTURES: list[Prefecture] = [
    # 北海道
    {"name": "札幌市", "name_en": "Sapporo", "lat": 43.0642, "lon": 141.3469, "region": "北海道"},
    # 東北
    {"name": "青森市", "name_en": "Aomori", "lat": 40.8222, "lon": 140.7474, "region": "東北"},
    {"name": "盛岡市", "name_en": "Morioka", "lat": 39.7036, "lon": 141.1527, "region": "東北"},
    {"name": "仙台市", "name_en": "Sendai", "lat": 38.2688, "lon": 140.8721, "region": "東北"},
    {"name": "秋田市", "name_en": "Akita", "lat": 39.7200, "lon": 140.1025, "region": "東北"},
    {"name": "山形市", "name_en": "Yamagata", "lat": 38.2404, "lon": 140.3636, "region": "東北"},
    {"name": "福島市", "name_en": "Fukushima", "lat": 37.7608, "lon": 140.4748, "region": "東北"},
    # 関東
    {"name": "水戸市", "name_en": "Mito", "lat": 36.3418, "lon": 140.4468, "region": "関東"},
    {"name": "宇都宮市", "name_en": "Utsunomiya", "lat": 36.5658, "lon": 139.8836, "region": "関東"},
    {"name": "前橋市", "name_en": "Maebashi", "lat": 36.3911, "lon": 139.0608, "region": "関東"},
    {"name": "さいたま市", "name_en": "Saitama", "lat": 35.8617, "lon": 139.6455, "region": "関東"},
    {"name": "千葉市", "name_en": "Chiba", "lat": 35.6074, "lon": 140.1065, "region": "関東"},
    {"name": "東京", "name_en": "Tokyo", "lat": 35.6895, "lon": 139.6917, "region": "関東"},
    {"name": "横浜市", "name_en": "Yokohama", "lat": 35.4478, "lon": 139.6425, "region": "関東"},
    # 中部
    {"name": "新潟市", "name_en": "Niigata", "lat": 37.9162, "lon": 139.0364, "region": "中部"},
    {"name": "富山市", "name_en": "Toyama", "lat": 36.6953, "lon": 137.2113, "region": "中部"},
    {"name": "金沢市", "name_en": "Kanazawa", "lat": 36.5613, "lon": 136.6562, "region": "中部"},
    {"name": "福井市", "name_en": "Fukui", "lat": 36.0652, "lon": 136.2216, "region": "中部"},
    {"name": "甲府市", "name_en": "Kofu", "lat": 35.6635, "lon": 138.5683, "region": "中部"},
    {"name": "長野市", "name_en": "Nagano", "lat": 36.6486, "lon": 138.1948, "region": "中部"},
    {"name": "岐阜市", "name_en": "Gifu", "lat": 35.4232, "lon": 136.7608, "region": "中部"},
    {"name": "静岡市", "name_en": "Shizuoka", "lat": 34.9769, "lon": 138.3831, "region": "中部"},
    {"name": "名古屋市", "name_en": "Nagoya", "lat": 35.1815, "lon": 136.9066, "region": "中部"},
    # 近畿
    {"name": "津市", "name_en": "Tsu", "lat": 34.7303, "lon": 136.5086, "region": "近畿"},
    {"name": "大津市", "name_en": "Otsu", "lat": 35.0045, "lon": 135.8686, "region": "近畿"},
    {"name": "京都市", "name_en": "Kyoto", "lat": 35.0211, "lon": 135.7556, "region": "近畿"},
    {"name": "大阪市", "name_en": "Osaka", "lat": 34.6937, "lon": 135.5023, "region": "近畿"},
    {"name": "神戸市", "name_en": "Kobe", "lat": 34.6913, "lon": 135.1830, "region": "近畿"},
    {"name": "奈良市", "name_en": "Nara", "lat": 34.6851, "lon": 135.8048, "region": "近畿"},
    {"name": "和歌山市", "name_en": "Wakayama", "lat": 34.2260, "lon": 135.1675, "region": "近畿"},
    # 中国
    {"name": "鳥取市", "name_en": "Tottori", "lat": 35.5036, "lon": 134.2381, "region": "中国"},
    {"name": "松江市", "name_en": "Matsue", "lat": 35.4681, "lon": 133.0485, "region": "中国"},
    {"name": "岡山市", "name_en": "Okayama", "lat": 34.6618, "lon": 133.9344, "region": "中国"},
    {"name": "広島市", "name_en": "Hiroshima", "lat": 34.3853, "lon": 132.4553, "region": "中国"},
    {"name": "山口市", "name_en": "Yamaguchi", "lat": 34.1861, "lon": 131.4706, "region": "中国"},
    # 四国
    {"name": "徳島市", "name_en": "Tokushima", "lat": 34.0658, "lon": 134.5593, "region": "四国"},
    {"name": "高松市", "name_en": "Takamatsu", "lat": 34.3401, "lon": 134.0434, "region": "四国"},
    {"name": "松山市", "name_en": "Matsuyama", "lat": 33.8416, "lon": 132.7657, "region": "四国"},
    {"name": "高知市", "name_en": "Kochi", "lat": 33.5597, "lon": 133.5311, "region": "四国"},
    # 九州
    {"name": "福岡市", "name_en": "Fukuoka", "lat": 33.5904, "lon": 130.4017, "region": "九州"},
    {"name": "佐賀市", "name_en": "Saga", "lat": 33.2635, "lon": 130.3008, "region": "九州"},
    {"name": "長崎市", "name_en": "Nagasaki", "lat": 32.7503, "lon": 129.8777, "region": "九州"},
    {"name": "熊本市", "name_en": "Kumamoto", "lat": 32.7898, "lon": 130.7417, "region": "九州"},
    {"name": "大分市", "name_en": "Oita", "lat": 33.2382, "lon": 131.6126, "region": "九州"},
    {"name": "宮崎市", "name_en": "Miyazaki", "lat": 31.9111, "lon": 131.4239, "region": "九州"},
    {"name": "鹿児島市", "name_en": "Kagoshima", "lat": 31.5602, "lon": 130.5581, "region": "九州"},
    # 沖縄
    {"name": "那覇市", "name_en": "Naha", "lat": 26.2124, "lon": 127.6809, "region": "沖縄"},
]

REGION_VIEWS: dict[str, ViewState] = {
    "全国": {"latitude": 37.0, "longitude": 137.0, "zoom": 4.5, "pitch": 45, "bearing": 0},
    "関東": {"latitude": 35.7, "longitude": 139.7, "zoom": 7.0, "pitch": 50, "bearing": 0},
    "九州": {"latitude": 32.5, "longitude": 130.5, "zoom": 6.0, "pitch": 50, "bearing": 0},
    "沖縄": {"latitude": 26.3, "longitude": 127.8, "zoom": 8.0, "pitch": 50, "bearing": 0},
    "北海道": {"latitude": 43.5, "longitude": 142.5, "zoom": 6.0, "pitch": 45, "bearing": 0},
    "近畿": {"latitude": 34.8, "longitude": 135.5, "zoom": 7.0, "pitch": 50, "bearing": 0},
}
