#!/usr/bin/env python3
"""
Учёт расходов: токены, модели, время агента и человека по активному проекту.

  python3 scripts/usage.py hook            # хук stop (Cursor и Claude Code): токены и модель каждого ответа
  python3 scripts/usage.py human 25 "выбор варианта"        # минуты работы человека
  python3 scripts/usage.py cursor-tokens 16400000 "Usage за 10.11"   # токены за период до хука (панель Usage)
  python3 scripts/usage.py cursor-usd 0 "подписка Pro"      # деньги сверх подписки, если были
  python3 scripts/usage.py exclude <conversation_id> "чат не по проекту"  # не считать чужой чат
  python3 scripts/usage.py report          # сводка → output/costs.md

Cursor передаёт токены и модель в хук stop (с 11.11.2026); за более ранние дни токены вносят по
панели Usage на cursor.com. Цены — scripts/prices.json (USD за 1 млн токенов).
"""
import json
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE = ROOT / ".active_project"


def _fallback_project(projects_dir):
    """Если .active_project нет (свежая копия репозитория): берём проект с самым свежим реестром."""
    cands = [d for d in projects_dir.iterdir()
             if d.is_dir() and not d.name.startswith("_") and (d / "ledger.json").exists()]
    if not cands:
        return None
    return max(cands, key=lambda d: (d / "ledger.json").stat().st_mtime).name


def active_dir():
    if ACTIVE.exists():
        name = ACTIVE.read_text(encoding="utf-8").strip()
    else:
        name = _fallback_project(ROOT / "projects")
    if not name:
        return None
    d = ROOT / "projects" / name
    return d if d.exists() else None


def parse_transcript(path):
    """Суммирует usage по моделям; одно сообщение считается один раз."""
    totals, seen = {}, set()
    files = [Path(path)]
    sub = Path(path).with_suffix("") / "subagents"      # транскрипты субагентов, если есть
    if sub.exists():
        files += sorted(sub.glob("*.jsonl"))
    first = last = None
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ts = e.get("timestamp")
            if ts:
                first = first or ts
                last = ts
            m = e.get("message") or {}
            u = m.get("usage")
            if not u:
                continue
            key = m.get("id") or e.get("uuid")
            if key in seen:
                continue
            seen.add(key)
            t = totals.setdefault(m.get("model", "unknown"), {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0})
            t["input"] += u.get("input_tokens", 0) or 0
            t["output"] += u.get("output_tokens", 0) or 0
            t["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
            t["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
    return totals, first, last


def cost(totals):
    pf = ROOT / "scripts" / "prices.json"
    prices = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    usd = 0.0
    unknown = []
    for model, t in totals.items():
        p = next((v for k, v in prices.items() if not k.startswith("_") and k in model), None)
        if not p:
            unknown.append(model)
            continue
        usd += (t["input"] * p["input"] + t["output"] * p["output"] +
                t["cache_write"] * p.get("cache_write", p["input"]) +
                t["cache_read"] * p.get("cache_read", p["input"] * 0.1)) / 1e6
    return round(usd, 4), unknown


def _debug(kind, inp):
    """Диагностика хуков: какое событие пришло и с какими полями (без значений, кроме служебных)."""
    import os
    d = active_dir()
    if not d or not os.environ.get("STRAT_HOOK_DEBUG"):
        return
    (d / "costs").mkdir(exist_ok=True)
    keep = {k: inp.get(k) for k in ("hook_event_name", "model", "reason", "duration_ms") if k in inp}
    with open(d / "costs" / "_hooks.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds"), "call": kind,
                            "keys": sorted(inp), **keep}, ensure_ascii=False) + "\n")


def hook():
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return
    _debug("hook", inp)
    if "input_tokens" in inp:          # Cursor: хук stop сам передаёт токены и модель ответа
        cursor_turn(inp)
        return
    d = active_dir()
    tp = inp.get("transcript_path")
    if not d or not tp or not Path(tp).exists():
        return
    totals, first, last = parse_transcript(tp)
    usd, unknown = cost(totals)
    out = d / "costs"
    out.mkdir(exist_ok=True)
    # файл на сессию перезаписывается — повторный вызов хука не удваивает счёт
    (out / f"{inp.get('session_id', 'unknown')}.json").write_text(json.dumps({
        "session_id": inp.get("session_id"), "updated": dt.datetime.now().isoformat(timespec="seconds"),
        "first": first, "last": last, "models": totals, "usd": usd, "unpriced_models": unknown,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def cursor_turn(inp):
    """Cursor, событие stop: одна строка на ответ агента (токены, модель). Повтор по generation_id не дублируется."""
    d = active_dir()
    if not d:
        return
    out = d / "costs"
    out.mkdir(exist_ok=True)
    f = out / "cursor-turns.jsonl"
    gid = inp.get("generation_id")
    if gid and f.exists() and f'"generation_id": "{gid}"' in f.read_text(encoding="utf-8"):
        return
    row = {"at": dt.datetime.now().isoformat(timespec="seconds"), "conversation_id": inp.get("conversation_id"),
           "generation_id": gid, "model": inp.get("model") or inp.get("model_id"), "status": inp.get("status"),
           "input": inp.get("input_tokens") or 0, "output": inp.get("output_tokens") or 0,
           "cache_read": inp.get("cache_read_tokens") or 0, "cache_write": inp.get("cache_write_tokens") or 0}
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def cursor_session():
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return
    _debug("cursor-session", inp)
    d = active_dir()
    if not d:
        return
    out = d / "costs"
    out.mkdir(exist_ok=True)
    sid = inp.get("session_id") or inp.get("conversation_id") or "unknown"
    (out / f"cursor-{sid}.json").write_text(json.dumps({
        "session_id": sid, "env": "cursor", "ended": dt.datetime.now().isoformat(timespec="seconds"),
        "minutes": round((inp.get("duration_ms") or 0) / 60000, 1), "model": inp.get("model"),
        "reason": inp.get("reason"), "background": inp.get("is_background_agent"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def manual(kind):
    d = active_dir()
    if not d or len(sys.argv) < 3:
        print("Использование: usage.py human <минуты> \"что делал\" | usage.py cursor-usd <сумма> \"откуда\"")
        return
    out = d / "costs"
    out.mkdir(exist_ok=True)
    f = out / "manual.json"
    rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    if kind == "exclude":
        rows.append({"at": dt.datetime.now().isoformat(timespec="seconds"), "kind": kind,
                     "conversation": sys.argv[2], "value": 0, "note": " ".join(sys.argv[3:])})
    else:
        rows.append({"at": dt.datetime.now().isoformat(timespec="seconds"), "kind": kind,
                     "value": float(sys.argv[2].replace(",", ".").replace(" ", "")), "note": " ".join(sys.argv[3:])})
    f.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Записано: {kind} {sys.argv[2]}")


def minutes(a, b):
    try:
        f = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return round((f(b) - f(a)).total_seconds() / 60, 1)
    except Exception:
        return 0


def report():
    d = active_dir()
    if not d:
        print("Нет активного проекта.")
        return
    rows, tot_usd, tot_min, tot_tok = [], 0, 0, 0
    cur_rows, human, cur_usd, man_tok, excluded = [], [], 0.0, [], {}
    for f in sorted((d / "costs").glob("*.json")) if (d / "costs").exists() else []:
        s = json.loads(f.read_text(encoding="utf-8"))
        if f.name == "manual.json":
            human = [r for r in s if r["kind"] == "human"]
            cur_usd = sum(r["value"] for r in s if r["kind"] == "cursor-usd")
            man_tok = [r for r in s if r["kind"] == "cursor-tokens"]
            excluded = {r["conversation"]: r["note"] for r in s if r["kind"] == "exclude"}
            continue
        if s.get("env") == "cursor":
            cur_rows.append(s)
            continue
        tok = sum(sum(t.values()) for t in s["models"].values())
        mins = minutes(s["first"], s["last"]) if s.get("first") and s.get("last") else 0
        rows.append((s["first"] or "?", s["session_id"][:8], ", ".join(s["models"]), tok, mins, s["usd"]))
        tot_usd += s["usd"]; tot_min += mins; tot_tok += tok
    L = [f"# Расходы проекта {d.name}", ""]
    if rows:
        L += ["**Claude Code — по сессиям**", "",
              "| начало | сессия | модели | токены | минут | ≈ USD |", "|---|---|---|---|---|---|"]
        L += [f"| {r[0][:16]} | {r[1]} | {r[2]} | {r[3]:,} | {r[4]} | {r[5]} |" for r in rows]
    if cur_rows:
        L += ["", "**Сессии Cursor**", "", "| завершена | сессия | модель | минут |", "|---|---|---|---|"]
        L += [f"| {r['ended'][:16]} | {r['session_id'][:8]} | {r.get('model') or '?'} | {r['minutes']} |" for r in cur_rows]
        tot_min += sum(r["minutes"] for r in cur_rows)
    turns_f = d / "costs" / "cursor-turns.jsonl"
    turns = [json.loads(x) for x in turns_f.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if turns_f.exists() else []
    skipped = [t for t in turns if t.get("conversation_id") in excluded]
    turns = [t for t in turns if t.get("conversation_id") not in excluded]
    cur_tok = cur_cache = 0
    if turns:
        by_model, convs = {}, {}
        for t in turns:
            m = by_model.setdefault(t["model"] or "?", {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "n": 0})
            for k in ("input", "output", "cache_write", "cache_read"):
                m[k] += t[k]
            m["n"] += 1
            convs.setdefault(t["conversation_id"], []).append(t["at"])
        L += ["", "**Cursor — по ответам агента (хук stop)**", "",
              "| модель | ответов | вход (в т.ч. из кэша) | выход | кэш: запись | кэш: чтение | всего = вход + выход |", "|---|---|---|---|---|---|---|"]
        for name, m in by_model.items():
            tot = m["input"] + m["output"]   # Cursor считает чтение из кэша внутри входа; так же считает панель Usage
            cur_tok += tot
            L.append(f"| {name} | {m['n']} | {m['input']:,} | {m['output']:,} | {m['cache_write']:,} | {m['cache_read']:,} | {tot:,} |")
        usd_t, unknown = cost({k: {kk: v[kk] for kk in ("input", "output", "cache_write", "cache_read")} for k, v in by_model.items()})
        tot_usd += usd_t
        # время работы: промежутки между соседними ответами; паузы дольше 20 мин (человек ушёл) не считаем
        spans = []
        for a in convs.values():
            a = sorted(a)
            spans.append(sum(g for g in (minutes(x, y) for x, y in zip(a, a[1:])) if g <= 20))
        cur_cache = sum(m["cache_read"] for m in by_model.values())
        tot_min += sum(spans)
        L.append("")
        L.append(f"Чатов: {len(convs)}; время работы агента ≈ {round(sum(spans))} мин (паузы дольше 20 мин не считаются).")
        if unknown:
            L.append(f"Цены для моделей {', '.join(unknown)} не заданы в `scripts/prices.json` — деньги по ним не посчитаны; "
                     "при подписке Cursor они входят в её цену.")
    if skipped:
        sk = sum(t["input"] + t["output"] for t in skipped)
        L.append(f"Не учтены чаты не по проекту: {len(excluded)} ({sk:,} токенов) — "
                 + "; ".join(f"{c[:8]}: {n}" for c, n in excluded.items()))
    mtok = sum(r["value"] for r in man_tok)
    if man_tok:
        L += ["", "**Cursor — до появления учёта в хуке (по панели Usage)**", ""]
        L += [f"- {r['at'][:10]}: {r['value']:,.0f} токенов — {r['note']}" for r in man_tok]
    hum = sum(r["value"] for r in human)
    if human:
        L += ["", "**Время человека**", ""] + [f"- {r['at'][:10]}: {r['value']:g} мин — {r['note']}" for r in human]
    usd = tot_usd + cur_usd
    all_tok = tot_tok + cur_tok + int(mtok)
    L += ["", "## Итого", "",
          f"- **Токены:** {all_tok:,}" + (f" (по хуку {cur_tok + tot_tok:,}, внесено по панели Usage {int(mtok):,})" if mtok else "")
          + (f"; из них повторное чтение контекста из кэша — {cur_cache:,} ({cur_cache / max(cur_tok, 1):.0%} учтённых хуком), оно в разы дешевле нового входа" if cur_cache else ""),
          f"- **Деньги сверх подписки:** ${cur_usd:g}" + (f"; Claude Code по ценам `prices.json` ≈ ${round(tot_usd, 2)}" if tot_usd else "")
          + "; подписки на среды (Cursor и др.) указываются отдельно",
          f"- **Время человека:** {round(hum)} мин" + (f"; работа агента ≈ {round(tot_min)} мин" if tot_min else ""),
          ]
    (d / "output" / "costs.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"hook": hook, "report": report, "cursor-session": cursor_session,
     "human": lambda: manual("human"), "cursor-usd": lambda: manual("cursor-usd"),
     "cursor-tokens": lambda: manual("cursor-tokens"), "exclude": lambda: manual("exclude")}.get(cmd, report)()
