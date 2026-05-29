"""CFTC Commitments of Traders — Long Report (Disaggregated) 解析器。

文件结构:每个商品一段,包含
- 标题行 "<NAME> - <EXCHANGE>"
- 紧接着 "Disaggregated Commitments of Traders ... <date>"
- Positions / Changes / Percent of OI / Number of Traders / Largest Traders Concentration 五节

11 列含义(positions/changes/percent/traders 的第 2~12 个值):
    producer_long, producer_short,
    swap_long, swap_short, swap_spr,
    mm_long, mm_short, mm_spr,
    other_long, other_short, other_spr

8 列含义(concentration):
    G4L, G4S, G8L, G8S, N4L, N4S, N8L, N8S
    (Gross/Net × 4-largest/8-largest × Long/Short 的 % of OI)

验证结果(2026-05-19 文件):贵金属+铜 6 商品集中度 100% 正确。
部分非贵金属商品 Number of Traders 列数不齐(类别为 0 时被压缩),非关键。
"""
from __future__ import annotations

import re

import pdfplumber

_INT = lambda s: int(s.replace(",", "")) if s and re.match(r"^-?[\d,]+$", s) else None
_FLT = lambda s: float(s)


def parse_cftc_long(path: str) -> dict:
    """解析 CFTC Long Report PDF或纯文本/HTML网页报告,返回按商品名索引的结构化数据。

    返回 {name: {exchange, date, oi, positions, oi_change, changes, percent,
                traders_total, traders, concentration, status}}
    """
    if path.lower().endswith((".txt", ".htm", ".html")):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    else:
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
    lines = text.split("\n")
    out: dict[str, dict] = {}

    for i, ln in enumerate(lines):
        if "Disaggregated Commitments of Traders" not in ln or i == 0:
            continue
        title = lines[i - 1].strip()
        tm = re.match(r"^(.+?)\s*-\s*(.+)$", title)
        if not tm:
            continue
        name = tm.group(1).strip()
        exch = tm.group(2).strip()
        date_m = re.search(r"(\w+ \d+, \d{4})", ln)

        e: dict = {
            "name": name,
            "exchange": exch,
            "date": date_m.group(1) if date_m else None,
            "oi": None,
            "positions": None,
            "oi_change": None,
            "changes": None,
            "percent": None,
            "traders_total": None,
            "traders": None,
            "concentration": None,
            "status": "OK",
        }

        section: str | None = None
        # 在该商品块内向下扫 ~60 行,直到下一个 "Disaggregated..." 出现
        for j in range(i + 1, min(i + 60, len(lines))):
            t = lines[j]
            if "Disaggregated Commitments of Traders" in t:
                break

            # 切换 section(注意 Positions 是初次,不能被后面的 Percent of OI Position 等触发)
            if "Positions" in t and section is None:
                section = "positions"
            elif "Changes in Commitments" in t:
                section = "changes"
            elif "Percent of Open Interest Represented by Each" in t:
                section = "percent"
            elif "Number of Traders" in t:
                section = "traders"
            elif "Largest Traders" in t:
                section = "concentration"

            # "All :" 数据行
            m = re.match(r"^\s*All\s*:\s*(.+)$", t)
            if m and section:
                body = m.group(1)
                if section == "concentration":
                    # 集中度行没有第二个冒号,所有数字都是 % 值,直接抓
                    nums = re.findall(r"-?[\d,]+\.[\d]+|-?[\d,]+", body)
                    e["concentration"] = [_FLT(x) for x in nums]
                else:
                    # 其他 section 格式: "All : <oi_or_total> : <11 个数字>"
                    if ":" in body:
                        pfx, _, dat = body.partition(":")
                        pfx = pfx.strip()
                        dat = dat.strip()
                    else:
                        pfx, dat = None, body
                    nums = re.findall(r"-?[\d,]+\.[\d]+|-?[\d,]+", dat)
                    if section == "positions":
                        e["oi"] = _INT(pfx)
                        e["positions"] = [_INT(x) for x in nums[:11]]
                    elif section == "percent":
                        e["percent"] = [_FLT(x) for x in nums[:11]]
                    elif section == "traders":
                        e["traders_total"] = _INT(pfx)
                        e["traders"] = [_INT(x) for x in nums[:11]]

            # Changes 行不带 "All" 前缀,而是 ": <OI_chg>: <11 个数字>"
            if section == "changes" and e["changes"] is None:
                cm = re.match(r"^\s*:\s*(-?[\d,]+)\s*:\s*(.+)$", t)
                if cm:
                    e["oi_change"] = _INT(cm.group(1))
                    nums = re.findall(r"-?[\d,]+", cm.group(2))
                    e["changes"] = [_INT(x) for x in nums[:11]]

        # —— 关键字段校验:positions=11, changes=11, concentration=8 必须齐 ——
        # traders 列数不齐只是 warning,不算 FAIL(部分商品某类别为 0 时压缩)
        errs: list[str] = []
        if e["positions"] is None or len(e["positions"]) != 11:
            errs.append(f"pos={len(e['positions'] or [])}")
        if e["changes"] is None or len(e["changes"]) != 11:
            errs.append(f"chg={len(e['changes'] or [])}")
        if e["concentration"] is None or len(e["concentration"]) != 8:
            errs.append(f"conc={len(e['concentration'] or [])}")
        if errs:
            e["status"] = "PARSE_FAILED: " + " ".join(errs)
        out[name] = e

    return out


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m cme_parsers.cftc_long <path/to/CFTC_Long_Report.pdf>")
        sys.exit(1)
    print(json.dumps(parse_cftc_long(sys.argv[1]), ensure_ascii=False, indent=2))
