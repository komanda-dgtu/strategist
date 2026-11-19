#!/usr/bin/env python3
"""
Размер и срок пилота — сколько участников нужно, чтобы заметить заданное улучшение доли, и успеем ли
набрать их за отведённое время (method/05-strategy.md, раздел 3.1). Только стандартная библиотека.

  python3 scripts/pilot.py --base 0.12 --target 0.09 --weekly 100 --weeks 6
  python3 scripts/pilot.py --base 0.42 --target 0.50,0.55,0.60 --weekly 150 --deff 1.2

  base    — доля в группе сравнения без изменений (например, 12% номеров с ограничением)
  target  — доля, которую считаем наименьшим важным для клиента улучшением (диапазон — через запятую)
  alpha   — допустимый риск увидеть пользу там, где её нет (по умолчанию 0,05, двусторонний)
  power   — вероятность заметить улучшение, если оно есть (по умолчанию 0,8)
  ratio   — доля пилотной группы среди включённых (по умолчанию 0,5 — поровну)
  deff    — поправка на группы: если распределяем семьи, а считаем номера, участники одной семьи
            похожи; 1 — независимые единицы (по умолчанию)
  weekly  — сколько впервые подходящих единиц появляется в неделю (необязательно)
  weeks   — сколько недель отведено на набор (необязательно)

Формула: сравнение двух долей, нормальное приближение. Число на группу
  n = (z₁₋α/₂·√(2·p̄·(1−p̄)) + z₁₋β·√(p₁(1−p₁) + p₂(1−p₂)))² / (p₁ − p₂)², затем × deff.
Добавьте --json, чтобы получить строки для model_result.json проекта.
"""
import argparse
import json
import math
from statistics import NormalDist


def nums(s):
    return [float(x) for x in str(s).replace(" ", "").split(",") if x != ""]


def sample_size(p1, p2, alpha=0.05, power=0.8, ratio=0.5, deff=1.0):
    """Нужное число единиц всего и в пилотной / контрольной группах."""
    if p1 == p2:
        return None
    z = NormalDist()
    za, zb = z.inv_cdf(1 - alpha / 2), z.inv_cdf(power)
    k = (1 - ratio) / ratio                      # контроль / пилот
    pbar = (p1 * k + p2) / (1 + k)
    # общий вид для неравных групп: n_pilot
    num = (za * math.sqrt(pbar * (1 - pbar) * (1 + 1 / k)) + zb * math.sqrt(p2 * (1 - p2) + p1 * (1 - p1) / k)) ** 2
    n_pilot = math.ceil(num / (p1 - p2) ** 2 * deff)
    n_ctrl = math.ceil(n_pilot * k)
    return {"base": p1, "target": p2, "abs_pp": (p2 - p1) * 100, "rel": (p2 - p1) / p1 if p1 else None,
            "alpha": alpha, "power": power, "deff": deff, "pilot": n_pilot, "control": n_ctrl,
            "total": n_pilot + n_ctrl}


def main():
    ap = argparse.ArgumentParser(description="Размер и срок пилота")
    ap.add_argument("--base", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--power", type=float, default=0.8)
    ap.add_argument("--ratio", type=float, default=0.5)
    ap.add_argument("--deff", type=float, default=1.0)
    ap.add_argument("--weekly", type=float)
    ap.add_argument("--weeks", type=float)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = []
    for p1 in nums(a.base):
        for p2 in nums(a.target):
            r = sample_size(p1, p2, a.alpha, a.power, a.ratio, a.deff)
            if r is None:
                continue
            if a.weekly:
                r["weeks_needed"] = r["total"] / a.weekly
            if a.weeks:
                r["weekly_needed"] = r["total"] / a.weeks
            rows.append(r)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    print("| было | цель | разница, п.п. | относительно | пилот | контроль | всего | недель набора | нужно в неделю |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        wn = f"{r['weeks_needed']:.1f}" if "weeks_needed" in r else "—"
        wk = f"{math.ceil(r['weekly_needed'])}" if "weekly_needed" in r else "—"
        rel = f"{r['rel']:+.0%}" if r["rel"] is not None else "—"
        print(f"| {r['base']:.1%} | {r['target']:.1%} | {r['abs_pp']:+.1f} | {rel} | {r['pilot']:,} | "
              f"{r['control']:,} | {r['total']:,} | {wn} | {wk} |")
    print(f"\nРиск ложной пользы {a.alpha:.0%}, вероятность заметить улучшение {a.power:.0%}"
          + (f", поправка на группы ×{a.deff:g}" if a.deff != 1 else "") + ".")
    if a.weekly and a.weeks:
        late = [r for r in rows if r["weeks_needed"] > a.weeks]
        if late:
            print(f"Не успеваем набрать за {a.weeks:g} нед. при {a.weekly:g} в неделю: "
                  + "; ".join(f"цель {r['target']:.0%} — нужно {r['weeks_needed']:.1f} нед." for r in late)
                  + " Варианты: дольше набор, больше поток, крупнее наименьшее важное улучшение "
                    "или проверять сначала понятность и исполнение, а не влияние на связь.")
    print("К сроку набора добавьте время наблюдения за последними участниками.")


if __name__ == "__main__":
    main()
