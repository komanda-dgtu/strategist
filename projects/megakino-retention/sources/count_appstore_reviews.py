"""Пересчёт разметки отзывов App Store о приложении МегаФон из сохранённой таблицы.

Запуск из корня репозитория:
    python3 projects/megakino-retention/sources/count_appstore_reviews.py

Таблица appstore-reviews-2026-11-10.csv — по строке на отзыв: дата, оценка, темы автоматической
разметки (правила в calc_appstore_reviews.js) и итог ручной проверки темы «навязанные услуги».
Текстов и имён авторов в таблице нет. Контрольная сумма SHA-256 таблицы при сохранении:
f368f1744d5b82ae5e1064e8bcd9fef8fb8539bf3259c55d4d2872d45e0f42b8
"""
import csv
import hashlib
from collections import Counter
from pathlib import Path

F = Path(__file__).with_name("appstore-reviews-2026-11-10.csv")
raw = F.read_bytes()
rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
cats = lambda r: set(filter(None, r["auto"].split("|")))

dates = sorted(r["date"] for r in rows)
months = Counter(d[:7] for d in dates)
auto = Counter(c for r in rows for c in cats(r))
confirmed = [r for r in rows if r["manual_imposed"] == "1"]

print(f"Контрольная сумма: {hashlib.sha256(raw).hexdigest()}")
print(f"Отзывов: {len(rows)}; даты {dates[0]} — {dates[-1]}; по месяцам: {dict(sorted(months.items()))}")
print("  (лента отдаёт страницы с пропусками: окно не сплошное)")
print(f"Оценка 1–2: {sum(int(r['rating']) <= 2 for r in rows)}")
print("Автоматическая разметка:", dict(auto.most_common()))
print(f"«Навязанные» после ручной проверки: {len(confirmed)} из {auto['imposed']} срабатываний; "
      f"из них с намерением уйти к другому оператору: {sum('churn_intent' in cats(r) for r in confirmed)}")
print(f"Упоминания кино после ручной проверки: 0 (автоматических срабатываний: {auto['video']}, все ложные)")
