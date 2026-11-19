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

3) Разрыв до цели: сколько единиц дополнительной прибыли нужно, чтобы закрыть разрыв (и покрыть новые
   прямые расходы), и сколько это на одного клиента.
     python3 scripts/breakeven.py gap --gap 6000000 --unit 500 --costs 0,1500000 --clients 2000,5000
   gap      — разрыв прибыли до цели, ₽ (например, цель 285 − без изменений 279 млн = 6 млн)
   unit     — прибыль за единицу (например, 500 ₽ за дополнительный оплаченный месяц номера)
   costs    — новые прямые расходы за тот же период, ₽ (необязательно)
   clients  — сколько клиентов получат услугу (необязательно: для ответа «месяцев на клиента»)
   Формула: нужно единиц = (gap + costs) / unit. В costs — только новые прямые расходы года; разработка — в payback.

4) Окупаемость разработки: по кварталам — дополнительная прибыль после прямых расходов; в каком квартале
   накопленная сумма покроет вложения, и какую сумму вложений вернёт весь горизонт.
     python3 scripts/breakeven.py payback --quarterly 0,250000,900000,1500000 --invest 2000000,3000000
   quarterly — дополнительная прибыль по кварталам после прямых расходов, ₽ (через запятую, по порядку)
   invest    — вложения в разработку, ₽ (необязательно: без него — только предельная сумма за горизонт)

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
    g = sp.add_parser("gap"); g.add_argument("--gap", required=True); g.add_argument("--unit", required=True)
    g.add_argument("--costs", default="0"); g.add_argument("--clients"); g.add_argument("--json", action="store_true")
    pb = sp.add_parser("payback"); pb.add_argument("--quarterly", required=True); pb.add_argument("--invest")
    pb.add_argument("--json", action="store_true")
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
    elif a.mode == "payback":
        q = nums(a.quarterly)
        cum, acc = [], 0.0
        for v in q:
            acc += v; cum.append(acc)
        for inv in (nums(a.invest) if a.invest else [None]):
            back = next((i + 1 for i, c in enumerate(cum) if inv is not None and c >= inv), None)
            rows.append({"invest": inv, "cumulative": cum, "payback_quarter": back, "max_invest": cum[-1] if cum else 0})
        if not a.json:
            print("| квартал | доп. прибыль, ₽ | накоплено, ₽ |")
            print("|---|---|---|")
            for i, (v, c) in enumerate(zip(q, cum)):
                print(f"| {i + 1} | {v:,.0f} | {c:,.0f} |")
            print(f"\nЗа {len(q)} кв. вернётся не больше {cum[-1]:,.0f} ₽ вложений (предельная сумма).")
            for x in rows:
                if x["invest"] is not None:
                    print(f"Вложения {x['invest']:,.0f} ₽: " + (f"окупаются в {x['payback_quarter']}-м квартале."
                          if x["payback_quarter"] else "за горизонт не окупаются."))
    elif a.mode == "gap":
        cl = nums(a.clients) if a.clients else [None]
        for gp, un, co, c in itertools.product(nums(a.gap), nums(a.unit), nums(a.costs), cl):
            need = (gp + co) / un
            rows.append({"gap": gp, "unit": un, "costs": co, "units_needed": need, "clients": c,
                         "per_client": need / c if c else None})
        if not a.json:
            print("| разрыв, ₽ | прибыль за единицу, ₽ | новые расходы, ₽ | нужно единиц | клиентов | единиц на клиента |")
            print("|---|---|---|---|---|---|")
            for x in rows:
                pc = f"{x['per_client']:.2f} | " if x["per_client"] is not None else ""
                c = f"{x['clients']:,.0f} | " if x["clients"] else "— | "
                print(f"| {x['gap']:,.0f} | {x['unit']:,.0f} | {x['costs']:,.0f} | {x['units_needed']:,.0f} | {c}{pc or '— |'}")
            print("\nЕсли единиц на клиента больше, чем месяцев услуги в плановом году, цель этой услугой не достигается.")
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
