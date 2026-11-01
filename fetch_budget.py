#!/usr/bin/env python3
"""国の補助金3事業の「予算に対する申請額の割合」を、公式サイトから取得して予算の使用状況.json に保存する。

- 取得先: 先進的窓リノベ2026 / 給湯省エネ2026 / みらいエコ住宅2026(リフォーム) の公式トップページ(毎日午前中に更新される)
- 取れなかった項目は、前回の値を残して ok=false・理由つきにする(古い値を新しい値として見せない)。
- 履歴は 予算消化率の履歴.csv に、日付ごとに1行ずつ追記する。
"""
import csv, datetime as dt, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "budget.json")
HIST = os.path.join(HERE, "budget_history.csv")
UA = "Mozilla/5.0 (compatible; subsidy-status-check/1.0)"

SITES = {
    "window": ("先進的窓リノベ2026", "https://window-renovation2026.env.go.jp/"),
    "kyuto": ("給湯省エネ2026", "https://kyutou-shoene2026.meti.go.jp/"),
    "mirai_reform": ("みらいエコ住宅2026（リフォーム）", "https://mirai-eco2026.mlit.go.jp/"),
}


def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        html = r.read().decode("utf-8", errors="ignore")
    html = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def asof(text):
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*午前\s*(\d{1,2})時\s*時点", text)
    if not m:
        raise RuntimeError("「○年○月○日 午前○時時点」の記載が見つかりません（ページの形式が変わった可能性）")
    y, mo, d, h = map(int, m.groups())
    return dt.datetime(y, mo, d, h).isoformat(timespec="minutes")


def pcts(text, pattern):
    return [int(x) for x in re.findall(pattern, text)]


def parse(key, text):
    if "予算" not in text:
        raise RuntimeError("ページに「予算」の記載がありません")
    out = {"asof": asof(text)}
    if key == "window":
        v = pcts(text, r"（概算値）\s*(\d{1,3})\s*％")
        if len(v) != 1:
            raise RuntimeError(f"割合の数が想定と違います: {v}")
        out["pct"] = v[0]
    elif key == "kyuto":
        v = pcts(text, r"（概算値）\s*(\d{1,3})\s*％")
        if len(v) != 2:
            raise RuntimeError(f"割合の数が想定と違います: {v}")
        out["pct"], out["removal_pct"] = v
    elif key == "mirai_reform":
        v = pcts(text, r"0%\s*100%\s*(\d{1,3})\s*％")
        if len(v) != 3:
            raise RuntimeError(f"割合の数が想定と違います（新築2＋リフォーム1のはず）: {v}")
        out["pct"] = v[2]  # 順序: GX志向型・長期優良/ZEH水準・リフォーム
    for k in ("pct", "removal_pct"):
        if k in out and not (0 <= out[k] <= 100):
            raise RuntimeError(f"{k}={out[k]} は0〜100の範囲外です")
    return out


def main():
    now = dt.datetime.now().astimezone()
    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8")).get("items", {})
        except Exception:
            prev = {}
    items, errors = {}, []
    for key, (label, url) in SITES.items():
        try:
            data = parse(key, get_text(url))
            age = (now.replace(tzinfo=None) - dt.datetime.fromisoformat(data["asof"])).days
            data.update(label=label, url=url, ok=True, stale=(age >= 3),
                        error=None, fetched_at=now.isoformat(timespec="seconds"))
            items[key] = data
        except Exception as e:  # 取れなかった: 前回値を残して印をつける
            old = dict(prev.get(key, {"label": label, "url": url}))
            old.update(label=label, url=url, ok=False, error=str(e)[:200])
            items[key] = old
            errors.append(f"{label}: {e}")
    json.dump({"fetched_at": now.isoformat(timespec="seconds"), "items": items, "errors": errors},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # 履歴(日付ごとに1行)
    ok = all(items[k].get("ok") for k in items)
    if ok:
        today = items["window"]["asof"][:10]
        rows = list(csv.reader(open(HIST, encoding="utf-8"))) if os.path.exists(HIST) else []
        if not rows:
            rows = [["公式の時点", "窓リノベ(%)", "給湯省エネ(%)", "撤去加算(%)", "みらいエコ・リフォーム(%)"]]
        if not any(r and r[0] == today for r in rows[1:]):
            rows.append([today, items["window"]["pct"], items["kyuto"]["pct"],
                         items["kyuto"].get("removal_pct", ""), items["mirai_reform"]["pct"]])
            csv.writer(open(HIST, "w", encoding="utf-8", newline="")).writerows(rows)
    print("取得結果:", "全件OK" if ok else "一部失敗")
    for k, v in items.items():
        print(f"  {v['label']}: {v.get('pct')}% ({v.get('asof')}) ok={v['ok']}" + (f" ERROR={v['error']}" if v.get('error') else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
