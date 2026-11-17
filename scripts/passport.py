#!/usr/bin/env python3
"""
Паспорт решения — одна страница для руководителя продукта, собранная из реестра.

  python3 scripts/passport.py          → projects/<активный>/output/00-passport.md

Ничего не придумывает: только то, что уже есть в ledger.json (и model_result.json, если
экономическая модель посчитана). Пересобирайте после каждого этапа и после пересмотра.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402

KIND = {"status_quo": "оставить как есть", "close": "закрыть направление", "change": "изменение"}


def short(t, n=120):
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def plain(t, n=120):
    """Текст для руководителя: без служебных меток методики вроде «NMT/» или «VP/RAT-3»."""
    t = " ".join((t or "").split())
    t = re.sub(r"^[A-Za-z]{2,5}/", "", t)
    t = re.sub(r"^RAT-\d+\s*", "", t)
    t = t[:1].upper() + t[1:]
    return short(t, n)


def proven(ratio):
    if ratio >= 0.75:
        return f"в основном проверено ({ratio:.0%})"
    if ratio >= 0.5:
        return f"наполовину проверено ({ratio:.0%})"
    return f"держится на гипотезах ({ratio:.0%} проверено)"


CORRECTION = ("ошиб", "неверно", "опечат", "указан не", "не тот", "перепутан")


def main():
    d = L.project_dir()
    data = L.load(d)
    meta = data.get("meta", {})
    act = lambda n: n.get("status", "active") == "active"  # noqa: E731
    chosen = meta.get("chosen", [])
    vs = L.verification_stats(data)

    out = [f"# Паспорт решения: {d.name}", "",
           f"_Собрано из реестра {L.now()[:16].replace('T', ' ')}. Не редактируйте вручную — пересоберите: "
           "`python3 scripts/passport.py`. Номера в скобках (C43, O3) — записи реестра; "
           "полный текст и источники — `evidence.md`._", "",
           f"**Вопрос:** {meta.get('request', '—')}", ""]

    # короткий ответ: почему + что делать + насколько проверено
    out += ["## Короткий ответ", ""]
    concl = [k for k in data["conclusions"] if act(k)]
    if concl:
        out.append("**Что мы поняли:**")
        for k in concl:
            _, total, ratio = L.strength(data, k["id"])
            tag = proven(ratio) if total else "без опор"
            out.append(f"- {plain(k['text'], 200)} — _{tag}_ ({k['id']})")
        out.append("")
    if meta.get("recommendation"):
        out.append(f"**Что делать:** {meta['recommendation']}")
        out.append(f"<sub>Выбор руководителя от {meta.get('chosen_at', '')[:10]}: {', '.join(chosen)}</sub>")
    else:
        out.append("**Что делать:** _руководитель ещё не выбрал вариант._")
    out.append("")
    facts = sum(1 for c in data["claims"] if act(c) and c["type"] == "fact")
    line = f"**Насколько это проверено:** {len(data['sources'])} источников, {facts} фактов; "
    if vs["total"]:
        line += (f"гипотез проверено {vs['checked']} из {vs['total']} — подтверждено {vs['confirmed']}, "
                 f"опровергнуто {vs['refuted']}, частично {vs['partial']}.")
    out += [line, ""]

    # варианты
    opts = [o for o in data["options"] if act(o)]
    if opts:
        out += ["## Варианты", "",
                "| Вариант | Тип | Проверенность опор | Возражений | Выбран |", "|---|---|---|---|---|"]
        for o in opts:
            _, total, ratio = L.strength(data, o["id"])
            nx = sum(1 for x in data["objections"] if x.get("target") == o["id"] and act(x))
            out.append(f"| {plain(o['text'], 90)} ({o['id']}) | {KIND.get(o.get('kind'), '')} | "
                       f"{ratio:.0%} | {nx} | {'✅' if o['id'] in chosen else ''} |")
        out += ["", "<sub>Проверенность опор — доля фактов, ввода руководителя и подтверждённых гипотез среди "
                "всех опор варианта. Это мера проверенности, а не качества: «оставить как есть» и «закрыть» "
                "опираются на сегодняшние факты, а варианты изменений — на гипотезы о будущем. Поэтому "
                "выбранный вариант изменений начинается с дешёвых проверок, а не с разработки.</sub>", ""]

    # экономика
    out += ["## Экономика", ""]
    mr = d / "model_result.json"
    if mr.exists():
        m = json.loads(mr.read_text(encoding="utf-8"))
        out.append(m.get("summary", "Модель посчитана — см. output/econ.md."))
        if m.get("flip"):
            out.append(f"**Что может поменять выбор:** {m['flip']}")
    else:
        out.append("_Не рассчитана: связь пользы с затратами и доходами пока описана словами "
                   "в стратегии._")
    out.append("")

    # что уже проверено
    checked = [c for c in data["claims"] if act(c) and c.get("verification")]
    if checked:
        out += ["## Что уже проверено", "", "| Гипотеза | Итог | Почему |", "|---|---|---|"]
        for c in checked:
            v = c["verification"]
            out.append(f"| {plain(c['text'], 90)} ({c['id']}) | {L.VERIFY_RESULTS[v['result']]} | "
                       f"{short(v.get('note') or '—', 110)} |")
        out.append("")

    # чего не знаем: непроверенные гипотезы, от которых зависит больше всего
    open_h = [c for c in data["claims"] if act(c) and c["type"] in ("hypothesis", "forecast")
              and (c.get("verification") or {}).get("result") not in ("confirmed", "refuted")]
    ranked = sorted(open_h, key=lambda c: -len([n for n in L.dependents(data, c["id"]) if act(n)]))
    crit = [c for c in ranked if L.dependents(data, c["id"])][:5]
    # Поручение команде попадает в пробелы, даже если на нём пока мало выводов:
    # проверка закрытыми данными не набирает связей в реестре.
    team = [c for c in ranked if (c.get("check") or "").startswith("Поручение команде")]
    seen = {c["id"] for c in crit}
    for c in team:
        if c["id"] not in seen:
            crit.append(c)
    if crit:
        out += ["## Чего мы не знаем и как проверить", "",
                "| Не проверено | Влияет на | Как проверить |", "|---|---|---|"]
        for c in crit:
            deps = [n["id"] for n in L.dependents(data, c["id"]) if act(n)]
            n = len(deps)
            affect = "1 запись" if n == 1 else f"{n} выводов, вариантов и решений"
            out.append(f"| {plain(c['text'], 100)} ({c['id']}) | {affect} "
                       f"| {short(c.get('check') or '—', 100)} |")
        if team:
            step = short(team[0].get("check") or team[0]["text"], 280)
        else:
            nxt = crit[0]
            step = f"Проверить: {plain(nxt['text'], 140)} — {short(nxt.get('check') or '', 200)}"
        out += ["", "## Следующий шаг", "", step, ""]

    # решения
    dec = [x for x in data["decisions"] if act(x)]
    out += ["## Решения", ""]
    if dec:
        out += ["| Решение | Кто отвечает | Как поймём | Когда пересмотреть |", "|---|---|---|---|"]
        for x in dec:
            when = x.get("review_date") or ""
            cond = short(x.get("review_if") or "", 90)
            out.append(f"| {short(x['text'], 120)} ({x['id']}) | {x.get('owner') or '—'} | "
                       f"{short(x.get('metric') or '—', 90)} | {(when + '; ') if when else ''}{cond} |")
    else:
        out.append("_Не зафиксированы (`/decide`)._")
    out.append("")

    # что изменилось — по существу; исправления записей — отдельной строкой
    # руководителю важны выбор, проверки, замены выводов и отзыв вариантов, выводов и решений;
    # отзыв отдельных записей и возражений — рабочая кухня, она остаётся в журнале ledger.json
    nodes = L.all_nodes(data)
    def substantive(e):
        if e["action"] in ("choose", "verify"):
            return True
        if e["action"] == "supersede":
            return e["id"][:1] in "KC"
        return e["action"] in ("revoked", "disputed") and e["id"][:1] in "OKD"
    events = [e for e in data["log"] if e["action"] in ("revoked", "disputed", "choose", "verify", "supersede")]
    fixes = [e for e in events if e["action"] == "revoked"
             and any(w in (e.get("detail") or "").lower() for w in CORRECTION)]
    real, seen = [], set()
    for e in reversed([e for e in events if e not in fixes and substantive(e)]):
        key = (e["action"], e["id"])
        if key in seen:                     # повторный выбор того же — показываем последний
            continue
        seen.add(key)
        real.append(e)
        if len(real) == 7:
            break
    if real or fixes:
        out += ["## Что менялось", ""]
        names = {"revoked": "отозвано", "disputed": "оспорено", "choose": "выбор", "verify": "проверка",
                 "supersede": "обновлено"}
        def line(e):
            what = plain((nodes.get(e["id"]) or {}).get("text") or "", 90) if e["action"] != "choose" else ""
            detail = e.get("detail") or ""
            if e["action"] == "verify":
                res, _, note = detail.partition(":")
                detail = f"{L.VERIFY_RESULTS.get(res.strip(), res)}:{note}"
            elif e["action"] == "supersede":
                m = re.match(r"→ (\S+);.*?;\s*(.*)$", detail)
                detail = f"заменено на {m.group(1)}: {m.group(2)}" if m else detail
            if e["action"] == "choose":
                return f"- {e['at'][:10]}: выбор руководителя {e['id'].replace(',', ', ')} (текст — в «Что делать»)"
            detail = short(detail, 120)
            return f"- {e['at'][:10]}: {names.get(e['action'], e['action'])} {e['id']}" + \
                (f" «{what}»" if what else "") + f" — {detail}"
        out += [line(e) for e in real]
        if fixes:
            out.append(f"- Исправлено ошибок в записях реестра: {len(fixes)} (неверные ссылки и источники; "
                       "подробности — в журнале `ledger.json`).")
        out.append("")

    p = d / "output" / "00-passport.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Записано: {p.relative_to(L.ROOT)}")


if __name__ == "__main__":
    main()
