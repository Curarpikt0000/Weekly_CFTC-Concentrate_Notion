"""CFTC Long Report 解析器测试。

锚定 2026-05-19 文件的贵金属+铜真实持仓与集中度。
"""
from __future__ import annotations

from cme_parsers.cftc_long import parse_cftc_long


def test_47_commodities_parsed(cftc_long_pdf):
    """文件共 47 个商品块,数量必须对得上。"""
    r = parse_cftc_long(str(cftc_long_pdf))
    assert len(r) == 47


def test_precious_metals_status_ok(cftc_long_pdf):
    """GOLD/SILVER/PLATINUM/PALLADIUM/COPPER 关键字段必须 status=OK。"""
    r = parse_cftc_long(str(cftc_long_pdf))
    for k in ("GOLD", "SILVER", "PLATINUM", "PALLADIUM"):
        assert k in r and r[k]["status"] == "OK", f"{k}: {r.get(k, {}).get('status')}"
    # COPPER 实际名字带 "- #1" 后缀
    copper = next(n for n in r if n.startswith("COPPER"))
    assert r[copper]["status"] == "OK"


def test_gold_known_values(cftc_long_pdf):
    """5/19 GOLD: OI=543,416, traders=310, 4-largest gross long=18.0%。"""
    r = parse_cftc_long(str(cftc_long_pdf))
    e = r["GOLD"]
    assert e["oi"] == 543_416
    assert e["traders_total"] == 310
    assert e["concentration"][0] == 18.0  # G4L


def test_palladium_concentration(cftc_long_pdf):
    """5/19 PALLADIUM 集中度: G4L=24.2 G4S=30.0 G8L=37.1 G8S=43.0 N4L=22.8 N4S=27.6 N8L=33.1 N8S=38.1。"""
    r = parse_cftc_long(str(cftc_long_pdf))
    assert r["PALLADIUM"]["concentration"] == [24.2, 30.0, 37.1, 43.0, 22.8, 27.6, 33.1, 38.1]


def test_11_columns_for_positions(cftc_long_pdf):
    """关键商品的 positions 与 changes 列数必须 == 11。"""
    r = parse_cftc_long(str(cftc_long_pdf))
    for k in ("GOLD", "SILVER", "PLATINUM", "PALLADIUM"):
        assert len(r[k]["positions"]) == 11
        assert len(r[k]["changes"]) == 11


def test_cftc_text_format(cftc_long_txt):
    """文本格式周报必须对账成功且成功解析出 GOLD, SILVER, PLATINUM, MICRO GOLD 为 OK。"""
    r = parse_cftc_long(str(cftc_long_txt))
    assert len(r) == 47
    for k in ("GOLD", "SILVER", "PLATINUM", "MICRO GOLD"):
        assert k in r and r[k]["status"] == "OK", f"{k}: {r.get(k, {}).get('status')}"
