#!/usr/bin/env python3
"""Свежие отзывы о приложении из открытого API RuStore — без имён авторов, номера телефонов скрыты.

    python3 bench/cascade/fetch_rustore.py            # приложение МегаФон, 300 отзывов
    python3 bench/cascade/fetch_rustore.py ru.megafon.mlk 300

Результат: bench/cascade/data/reviews.jsonl (папка data/ не публикуется: тексты пишут пользователи).
Короткие отзывы (меньше 15 символов) пропускаются — в них нечего размечать.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://backapi.rustore.ru/comment/comment?packageName={pkg}&pageNumber={p}&pageSize=20"
OUT = Path(__file__).resolve().parent / "data"


def fetch(pkg, n):
    out, p = [], 0
    while len(out) < n and p < 50:
        req = urllib.request.Request(URL.format(pkg=pkg, p=p), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            content = (json.load(r).get("body") or {}).get("content") or []
        if not content:
            break
        for x in content:
            t = (x.get("commentText") or "").strip()
            if len(t) < 15:
                continue
            t = re.sub(r"\+?\d[\d\s\-()]{6,}\d", "[номер]", t)      # телефоны и длинные номера
            out.append({"id": x["commentId"], "date": x["commentDate"][:10],
                        "rating": x["appRating"], "text": " ".join(t.split())})
        p += 1
    return out[:n]


if __name__ == "__main__":
    pkg = sys.argv[1] if len(sys.argv) > 1 else "ru.megafon.mlk"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    rows = fetch(pkg, n)
    OUT.mkdir(exist_ok=True)
    with open(OUT / "reviews.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    dates = sorted(r["date"] for r in rows)
    print(f"Отзывов: {len(rows)}, {dates[0]} — {dates[-1]} → {OUT / 'reviews.jsonl'}")
