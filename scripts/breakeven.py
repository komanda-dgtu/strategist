#!/usr/bin/env python3
"""
Пороги окупаемости — когда внутренних данных нет, считаем не прибыль, а «сколько должно измениться,
чтобы вариант окупился» (method/05-strategy.md, раздел 1.4). Только стандартная библиотека.

Числа можно задавать диапазоном через запятую — посчитаются все сочетания.

1) Удержание окупает затраты: на сколько должен снизиться отток, чтобы окупить новые затраты
   (или потерянный доход) на одного клиента в месяц.
     python3 scripts/breakeven.py retention --cost 104 --revenue 1600 --margin 0.425 --churn 0.02
   cost     — новые затраты или потерянный доход, ₽ на клиента в месяц
   revenue  — доход с клиента в месяц, ₽;  margin — доля маржи (0..1)
   churn    — текущий месячный отток (необязательно: нужен только для ответа в п.п.)
   Формула: относительное снижение оттока ≥ cost / (revenue × margin). От уровня оттока не зависит.

2) Цена: сколько клиентов можно потерять при повышении цены (или сколько нужно привлечь при снижении),
   чтобы маржа не упала.
     python3 scripts/breakeven.py price --old 299 --new 399 --unit-cost 200,260
   unit-cost — переменные затраты на клиента в месяц (например, доля партнёров), ₽
   Формула: допустимое изменение числа клиентов = (old − c) / (new − c) − 1.

Добавьте --json, чтобы получить строки результата для model_result.json проекта.
"""
import argparse
import itertools
import json


def nums(s):
    return [float(x) for x in str(s).replace(" ", "").split(",") if x != ""]


def retention(cost, revenue, margin, churn=None):
    """Нужное относительное снижение оттока (доля) и, если задан отток, в процентных пунктах."""
    rel = cost / (revenue * margin)
    out = {"cost": cost, "revenue": revenue, "margin": margin, "rel_drop": rel}
    if churn:
        out.update(churn=churn, pp=rel * churn * 100)
    return out


def price(old, new, unit_cost):
    """Допустимое изменение числа клиентов при смене цены, доля (−0,2 = можно потерять 20%)."""
    if new <= unit_cost:
        return {"old": old, "new": new, "unit_cost": unit_cost, "volume_change": None}
    return {"old": old, "new": new, "unit_cost": unit_cost, "volume_change": (old - unit_cost) / (new - unit_cost) - 1}


def main():
    ap = argparse.ArgumentParser(description="Пороги окупаемости")
    sp = ap.add_subparsers(dest="mode", required=True)
    r = sp.add_parser("retention"); r.add_argument("--cost", required=True); r.add_argument("--revenue", required=True)
    r.add_argument("--margin", required=True); r.add_argument("--churn"); r.add_argument("--json", action="store_true")
    p = sp.add_parser("price"); p.add_argument("--old", required=True); p.add_argument("--new", required=True)
    p.add_argument("--unit-cost", required=True); p.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = []
    if a.mode == "retention":
        churns = nums(a.churn) if a.churn else [None]
        for c, rv, m, ch in itertools.product(nums(a.cost), nums(a.revenue), nums(a.margin), churns):
            rows.append(retention(c, rv, m, ch))
        if not a.json:
            print("| затраты, ₽/мес | доход, ₽/мес | маржа | нужно снизить отток, относительно | при оттоке | в п.п. в месяц |")
            print("|---|---|---|---|---|---|")
            for x in rows:
                pp = f"{x['churn']:.1%} | {x['pp']:.2f}" if x.get("churn") else "— | —"
                print(f"| {x['cost']:g} | {x['revenue']:g} | {x['margin']:.1%} | {x['rel_drop']:.1%} | {pp} |")
            lo, hi = min(x["rel_drop"] for x in rows), max(x["rel_drop"] for x in rows)
            rng = f"{lo:.1%}" if abs(hi - lo) < 1e-9 else f"{lo:.1%}–{hi:.1%}"
            print(f"\nОкупается, если отток снизится на {rng} относительно."
                  + (" Больше 100% — не окупается ни при каком удержании." if hi > 1 else ""))
    else:
        for o, n, u in itertools.product(nums(a.old), nums(a.new), nums(a.unit_cost)):
            rows.append(price(o, n, u))
        if not a.json:
            print("| было, ₽ | стало, ₽ | затраты на клиента, ₽ | допустимое изменение числа клиентов |")
            print("|---|---|---|---|")
            for x in rows:
                v = "цена ниже затрат — убыток" if x["volume_change"] is None else f"{x['volume_change']:+.1%}"
                print(f"| {x['old']:g} | {x['new']:g} | {x['unit_cost']:g} | {v} |")
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
