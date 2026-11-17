#!/usr/bin/env python3
"""Делит отзывы на эталон для человека (30), обучающую (80) и тестовую выборки — детерминированно.

    python3 bench/cascade/make_sets.py

Пишет в bench/cascade/data/:
  gold_sheet.csv  — 30 отзывов для ручной разметки (заполнить столбцы q1, q2, q3);
  batch.jsonl     — все отзывы для разметки моделями (id и текст);
  split.json      — какие id в эталоне, обучающей и тестовой выборках.
"""
import csv
import json
import random
from pathlib import Path

D = Path(__file__).resolve().parent / "data"
rows = [json.loads(x) for x in (D / "reviews.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
ids = sorted(r["id"] for r in rows)
random.Random(42).shuffle(ids)
split = {"gold": ids[:30], "train": ids[30:110], "test": ids[110:]}
(D / "split.json").write_text(json.dumps(split, indent=1), encoding="utf-8")
by_id = {r["id"]: r for r in rows}
with open(D / "gold_sheet.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "text", "q1", "q2", "q3"])
    for i in split["gold"]:
        w.writerow([i, by_id[i]["text"], "", "", ""])
with open(D / "batch.jsonl", "w", encoding="utf-8") as f:
    for i in sorted(ids):
        f.write(json.dumps({"id": i, "text": by_id[i]["text"]}, ensure_ascii=False) + "\n")
print(f"Эталон {len(split['gold'])}, обучающая {len(split['train'])}, тестовая {len(split['test'])}. "
      f"Файл для ручной разметки: {D / 'gold_sheet.csv'}")
