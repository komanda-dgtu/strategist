#!/usr/bin/env python3
"""
Реестр утверждений проекта (evidence ledger).

Только стандартная библиотека Python 3.9+. Агент вызывает этот скрипт сам —
человеку не нужно ничего программировать.

Узлы реестра:
  S  source      источник (сайт, документ, таблица, интервью, синтетика)
  C  claim       утверждение: fact | hypothesis | forecast | opinion | synthetic | user_input | inference
                 opinion — чьё-то суждение или названная человеком цифра, не измерение
                 источник kind=method (прогон навыка-методологии) допускает только hypothesis/opinion
  K  conclusion  вывод исследования
  O  option      вариант: status_quo | close | change
  X  objection   сильное возражение к варианту
  F  feature     элемент продукта в выбранной стратегии
  P  promise     обещание коммуникационной стратегии (должно опираться на F)
  D  decision    принятое решение (ответственный, показатель, условие пересмотра)

Связи: поле based_on (на что опирается узел), для X — поле target (к какому варианту).

Примеры:
  python3 scripts/ledger.py new wallet-retention "Почему падает удержание в кошельке"
  python3 scripts/ledger.py add-source --title "Отчёт МегаФон 2025" --url https://... --kind doc
  python3 scripts/ledger.py add C --type fact --text "Выручка 525,6 млрд" --sources S1 --confidence high
  python3 scripts/ledger.py add K --text "..." --based-on C1,C2
  python3 scripts/ledger.py add O --kind status_quo --text "Оставить как есть" --based-on K1
  python3 scripts/ledger.py add X --target O1 --text "..." --based-on C3
  python3 scripts/ledger.py revoke C2 --reason "Новые данные: ..."
  python3 scripts/ledger.py impact C2
  python3 scripts/ledger.py validate
  python3 scripts/ledger.py report
  python3 scripts/ledger.py search кинопоиск цена
  python3 scripts/ledger.py choose O3,O4 --text "O3 основной трек, пилот O4"
  python3 scripts/ledger.py verify C43 --result refuted --sources S30 --note "в 120 отзывах нет жалоб на переключения"

Проверка гипотез (verify): гипотеза или прогноз получает итог проверки — confirmed (подтверждена),
refuted (опровергнута), partial (частично), inconclusive (данных не хватило) — со ссылкой на источник
проверки. Подтверждённая гипотеза засчитывается в силу оснований, опровергнутая — сигнал пересмотреть
всё, что на ней держится (ledger.py impact).
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
ACTIVE = ROOT / ".active_project"

PREFIX = {"S": "sources", "C": "claims", "K": "conclusions", "O": "options",
          "X": "objections", "F": "features", "P": "promises", "D": "decisions"}
CLAIM_TYPES = ["fact", "hypothesis", "forecast", "opinion", "synthetic", "user_input", "inference"]
# method — прогон методологического навыка (например, разбор по чек-листу из method/): его выводы — только гипотезы
SOURCE_KINDS = ["web", "doc", "table", "interview", "synthetic", "user", "image", "audio", "video", "method"]
METHOD_ALLOWED = {"hypothesis", "opinion"}
OPTION_KINDS = ["status_quo", "close", "change"]
STATUSES = ["active", "disputed", "revoked"]
VERIFY_RESULTS = {"confirmed": "подтверждена", "refuted": "опровергнута",
                  "partial": "подтверждена частично", "inconclusive": "данных не хватило"}
STALE_DAYS = 183
LABEL = {"fact": "ФАКТ", "hypothesis": "ГИПОТЕЗА", "forecast": "ПРОГНОЗ", "opinion": "МНЕНИЕ",
         "synthetic": "СИНТЕТИКА", "user_input": "ОТ ПОЛЬЗОВАТЕЛЯ", "inference": "ВЫВОД"}


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def die(msg):
    print("ОШИБКА: " + msg, file=sys.stderr)
    sys.exit(1)


# ---------- проект и файл реестра ----------

def _fallback_project(projects_dir):
    """Если .active_project нет (свежая копия репозитория): проект из projects/DEFAULT (демо для первого
    запуска), иначе — с самым свежим реестром; замеры (*-bench) и шаблоны (_*) не выбираются."""
    default = projects_dir / "DEFAULT"
    if default.exists():
        name = default.read_text(encoding="utf-8").strip()
        if name and (projects_dir / name / "ledger.json").exists():
            return name
    cands = [d for d in projects_dir.iterdir()
             if d.is_dir() and not d.name.startswith("_") and not d.name.endswith("-bench")
             and (d / "ledger.json").exists()]
    if not cands:
        return None
    return max(cands, key=lambda d: (d / "ledger.json").stat().st_mtime).name


def project_dir(name=None):
    if name is None and not ACTIVE.exists():
        name = _fallback_project(PROJECTS)
    if name is None:
        if not ACTIVE.exists():
            die("нет активного проекта. Создайте: ledger.py new <имя> \"<запрос>\" или выберите: ledger.py use <имя>")
        name = ACTIVE.read_text(encoding="utf-8").strip()
    d = PROJECTS / name
    if not d.exists():
        die(f"проект '{name}' не найден в projects/")
    return d


def empty_ledger():
    return {k: [] for k in PREFIX.values()} | {"log": []}


def load(d):
    p = d / "ledger.json"
    if not p.exists():
        return empty_ledger()
    data = json.loads(p.read_text(encoding="utf-8"))
    for k in list(PREFIX.values()) + ["log"]:
        data.setdefault(k, [])
    return data


def save(d, data):
    p = d / "ledger.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)  # атомарная запись: сбой не портит реестр


def all_nodes(data):
    out = {}
    for k in PREFIX.values():
        for n in data[k]:
            out[n["id"]] = n
    return out


def next_id(data, prefix):
    nums = [int(n["id"][1:]) for n in data[PREFIX[prefix]] if n["id"][1:].isdigit()]
    return f"{prefix}{max(nums, default=0) + 1}"


def split_ids(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def log(data, action, node_id, detail=""):
    data["log"].append({"at": now(), "action": action, "id": node_id, "detail": detail})


# ---------- команды ----------

def cmd_new(a):
    d = PROJECTS / a.name
    if d.exists():
        die(f"проект '{a.name}' уже существует")
    tpl = PROJECTS / "_template"
    d.mkdir(parents=True)
    (d / "sources").mkdir()
    (d / "output").mkdir()
    state = (tpl / "state.md").read_text(encoding="utf-8") if (tpl / "state.md").exists() else "# Состояние\n"
    state = state.replace("{{NAME}}", a.name).replace("{{REQUEST}}", a.request).replace("{{DATE}}", now())
    (d / "state.md").write_text(state, encoding="utf-8")
    data = empty_ledger()
    data["meta"] = {"name": a.name, "request": a.request, "created": now()}
    save(d, data)
    ACTIVE.write_text(a.name, encoding="utf-8")
    print(f"Создан проект projects/{a.name} и сделан активным.")


def cmd_use(a):
    project_dir(a.name)
    ACTIVE.write_text(a.name, encoding="utf-8")
    print(f"Активный проект: {a.name}")


def cmd_list(a):
    active = ACTIVE.read_text(encoding="utf-8").strip() if ACTIVE.exists() else ""
    for p in sorted(PROJECTS.iterdir()):
        if p.is_dir() and not p.name.startswith("_"):
            print(("* " if p.name == active else "  ") + p.name)


def cmd_add_source(a):
    d = project_dir()
    data = load(d)
    if a.kind not in SOURCE_KINDS:
        die(f"kind должен быть одним из {SOURCE_KINDS}")
    if not a.url and not a.file:
        die("нужен --url или --file (путь к сохранённому материалу в sources/)")
    for s0 in data["sources"]:
        if (a.url and s0.get("url") == a.url) or (a.file and not a.url and s0.get("file") == a.file and s0["title"] == a.title):
            print(f"{s0['id']} (источник уже зарегистрирован)")
            return
    sid = next_id(data, "S")
    data["sources"].append({"id": sid, "title": a.title, "url": a.url, "file": a.file,
                            "kind": a.kind, "published": a.published, "accessed": now(),
                            "note": a.note, "flag": None})
    log(data, "add", sid, a.title)
    save(d, data)
    print(sid)


def cmd_source_flag(a):
    d = project_dir()
    data = load(d)
    n = all_nodes(data).get(a.id)
    if not n or not a.id.startswith("S"):
        die(f"источник {a.id} не найден")
    n["flag"] = a.reason
    log(data, "flag", a.id, a.reason)
    save(d, data)
    print(f"{a.id} помечен: {a.reason}")


def cmd_add(a):
    d = project_dir()
    data = load(d)
    p = a.prefix.upper()
    if p not in PREFIX or p == "S":
        die("тип узла: C, K, O, X, F, P или D (источники — через add-source)")
    nodes = all_nodes(data)
    based = split_ids(a.based_on)
    srcs = split_ids(a.sources)
    for ref in based + srcs + ([a.target] if a.target else []):
        if ref not in nodes:
            die(f"ссылка на несуществующий узел {ref}")
    if p == "C" and a.type not in CLAIM_TYPES:
        die(f"--type обязателен для C: {CLAIM_TYPES}")
    node = {"id": next_id(data, p), "text": a.text, "status": "active",
            "based_on": based, "created": now(), "updated": now()}
    if p == "C":
        kinds = {nodes[s].get("kind") for s in srcs}
        if "method" in kinds and a.type not in METHOD_ALLOWED:
            die("вывод методологического навыка (источник kind=method) — это гипотеза или мнение, "
                f"а не '{a.type}'. Используйте --type hypothesis --check \"...\"")
        if a.type == "opinion" and not srcs:
            die("у мнения должен быть источник: чьё это суждение (--sources S..)")
    # защита от повторной записи (например, при продолжении после сбоя)
    if not a.force:
        for n in data[PREFIX[p]]:
            if n.get("status", "active") == "active" and norm(n["text"]) == norm(a.text):
                print(f"{n['id']} (уже есть — повторно не записано; --force, если это намеренно)")
                return
    if p == "C":
        node |= {"type": a.type, "sources": srcs, "confidence": a.confidence,
                 "check": a.check}
    if p == "O":
        if a.kind not in OPTION_KINDS:
            die(f"--kind обязателен для O: {OPTION_KINDS}")
        node["kind"] = a.kind
    if p == "X":
        if not a.target or not a.target.startswith("O"):
            die("для возражения нужен --target O<n>")
        node["target"] = a.target
    if p == "D":
        node |= {"option": a.target, "owner": a.owner, "metric": a.metric,
                 "review_if": a.review_if, "review_date": a.review_date}
    data[PREFIX[p]].append(node)
    log(data, "add", node["id"], a.text[:80])
    save(d, data)
    print(node["id"])
    # защита от ошибочной ссылки: показываем, на что на самом деле опирается новая запись
    for ref in based + ([a.target] if a.target else []):
        t = nodes[ref].get("text") or nodes[ref].get("title") or ""
        print(f"  ← {ref}: {t[:90]}")
    for ref in srcs:
        print(f"  ← {ref}: {(nodes[ref].get('title') or '')[:90]}")


def dependents(data, node_id):
    """Все узлы, которые прямо или косвенно опираются на node_id."""
    nodes = all_nodes(data)
    rev = {}
    for n in nodes.values():
        for ref in n.get("based_on", []) + n.get("sources", []) + ([n["target"]] if n.get("target") else []):
            rev.setdefault(ref, []).append(n["id"])
    seen, stack = [], [node_id]
    while stack:
        cur = stack.pop()
        for child in rev.get(cur, []):
            if child not in seen:
                seen.append(child)
                stack.append(child)
    return [nodes[i] for i in seen]


def leaf_claims(data, node_id):
    """Утверждения-«листья» (не выводы), на которых в итоге держится узел."""
    nodes = all_nodes(data)
    out, seen, stack = set(), set(), [node_id]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in nodes:
            continue
        seen.add(cur)
        n = nodes[cur]
        if cur != node_id and cur.startswith("C") and n.get("type") != "inference":
            out.add(cur)
            continue
        stack.extend(n.get("based_on", []))
    return out


def strength(data, node_id):
    """Сила оснований: доля опор-фактов (fact, user_input) среди всех опор узла."""
    nodes = all_nodes(data)
    leaves = [nodes[i] for i in leaf_claims(data, node_id) if nodes[i].get("status") != "revoked"]
    if not leaves:
        return 0, 0, 0.0
    def weight(n):
        if n["type"] in ("fact", "user_input"):
            return 1.0
        res = (n.get("verification") or {}).get("result")
        return {"confirmed": 1.0, "partial": 0.5}.get(res, 0.0)
    solid = sum(weight(n) for n in leaves)
    solid = int(solid) if solid == int(solid) else solid
    return solid, len(leaves), round(solid / len(leaves), 2)


def norm(s):
    return " ".join((s or "").lower().split())


def cmd_search(a):
    d = project_dir()
    data = load(d)
    words = [w.lower() for w in a.words]
    hits = 0
    for n in all_nodes(data).values():
        hay = norm(" ".join(str(n.get(k, "")) for k in ("text", "title", "note", "check", "url")))
        if all(w in hay for w in words):
            hits += 1
            label = n.get("type") or n.get("kind") or ""
            print(f"  {n['id']:5} [{n.get('status', n.get('flag') and 'flagged' or '')}] {label:11} "
                  f"{(n.get('text') or n.get('title'))[:110]}")
    print(f"Найдено: {hits}")


def cmd_choose(a):
    d = project_dir()
    data = load(d)
    nodes = all_nodes(data)
    ids = split_ids(a.ids)
    for i in ids:
        if i not in nodes or not i.startswith("O"):
            die(f"{i}: нужен id варианта O<n>")
    data.setdefault("meta", {}) .update({"chosen": ids, "recommendation": a.text, "chosen_at": now()})
    log(data, "choose", ",".join(ids), a.text[:80])
    save(d, data)
    print(f"Выбрано: {', '.join(ids)}")


def cmd_verify(a):
    d = project_dir()
    data = load(d)
    nodes = all_nodes(data)
    n = nodes.get(a.id)
    if not n or not a.id.startswith("C"):
        die(f"{a.id}: нужен id утверждения C<n>")
    if n.get("type") not in ("hypothesis", "forecast", "opinion", "synthetic"):
        die(f"{a.id} — {n.get('type')}: проверяют гипотезы, прогнозы, мнения и синтетику, а не факты")
    if a.result not in VERIFY_RESULTS:
        die(f"--result: {', '.join(VERIFY_RESULTS)}")
    srcs, based = split_ids(a.sources), split_ids(a.based_on)
    for ref in srcs + based:
        if ref not in nodes:
            die(f"ссылка на несуществующий узел {ref}")
    real = [s for s in srcs if nodes[s].get("kind") not in ("method", "synthetic")]
    solid = [b for b in based if nodes[b].get("type") in ("fact", "user_input")]
    if a.result != "inconclusive" and not (real or solid):
        die("итог проверки нужен с основанием: реальный источник (--sources S..) "
            "или факт (--based-on C..). Синтетика и прогон методики не проверяют гипотезу.")
    n["verification"] = {"result": a.result, "sources": srcs, "based_on": based,
                         "note": a.note, "at": now()}
    n["updated"] = now()
    log(data, "verify", a.id, f"{a.result}: {a.note or ''}"[:80])
    save(d, data)
    deps = [x for x in dependents(data, a.id) if x.get("status", "active") == "active"]
    print(f"{a.id}: итог проверки — {VERIFY_RESULTS[a.result]}.")
    if a.result in ("refuted", "partial") and deps:
        print(f"На неё опираются {len(deps)} узл.: {', '.join(x['id'] for x in deps[:12])}"
              f"{' …' if len(deps) > 12 else ''} — пересмотрите (ledger.py impact {a.id}).")


def verification_stats(data):
    hyps = [c for c in data["claims"] if c.get("status", "active") == "active"
            and c["type"] in ("hypothesis", "forecast")]
    res = [(c.get("verification") or {}).get("result") for c in hyps]
    return {"total": len(hyps), "checked": sum(1 for r in res if r),
            **{k: res.count(k) for k in VERIFY_RESULTS}}


def cmd_revoke(a, status="revoked"):
    d = project_dir()
    data = load(d)
    n = all_nodes(data).get(a.id)
    if not n:
        die(f"узел {a.id} не найден")
    if a.id.startswith("S"):
        n["flag"] = (n.get("flag") or "") + f" отозван: {a.reason}"
    else:
        n["status"] = status
        n["status_reason"] = a.reason
        n["updated"] = now()
    log(data, status, a.id, a.reason)
    save(d, data)
    print(f"{a.id} → {status}. Затронуто узлов: {len(dependents(data, a.id))}. Подробнее: ledger.py impact {a.id}")


def cmd_supersede(a):
    """Заменить устаревшее утверждение свежим: прямые опоры переводятся на новое, старое отзывается.
    Связи не рвутся, а пересмотр по смыслу остаётся за агентом — скрипт печатает, что проверить."""
    d = project_dir()
    data = load(d)
    nodes = all_nodes(data)
    old, new = nodes.get(a.id), nodes.get(a.by)
    if not old or not new:
        die("нужны существующие id: устаревшее и свежее утверждение")
    if a.id[0] != a.by[0] or a.id[0] not in "CK":
        die("заменять можно утверждение утверждением (C) или вывод выводом (K)")
    if new.get("status", "active") != "active":
        die(f"{a.by} не активно — замена должна быть действующей записью")
    moved = []
    for n in nodes.values():
        if n is new or n.get("status", "active") != "active":
            continue
        refs = n.get("based_on", [])
        if a.id in refs:
            n["based_on"] = [a.by if r == a.id else r for r in refs]
            n["based_on"] = list(dict.fromkeys(n["based_on"]))
            n["updated"] = now()
            moved.append(n)
    old["status"] = "revoked"
    old["status_reason"] = f"заменено свежим {a.by}: {a.reason}"
    old["superseded_by"] = a.by
    old["updated"] = now()
    log(data, "supersede", a.id, f"→ {a.by}; опоры переведены: {', '.join(n['id'] for n in moved) or 'нет'}; {a.reason}")
    save(d, data)
    print(f"{a.id} заменено на {a.by}. Опоры переведены у {len(moved)} записей.")
    print(f"  было: {old['text'][:110]}")
    print(f"  стало: {new['text'][:110]}")
    if moved:
        print("Проверь по смыслу — меняет ли свежее сведение их вывод (если да: revoke и запиши заново):")
        for n in moved:
            print(f"  {n['id']:5} {n['text'][:110]}")


def cmd_impact(a):
    d = project_dir()
    data = load(d)
    if a.id not in all_nodes(data):
        die(f"узел {a.id} не найден")
    deps = dependents(data, a.id)
    if not deps:
        print(f"На {a.id} ничего не опирается.")
        return
    print(f"На {a.id} опираются ({len(deps)}) — их нужно пересмотреть:")
    for n in deps:
        print(f"  {n['id']:5} [{n.get('status','')}] {(n.get('text') or n.get('title') or '')[:100]}")


def cmd_validate(a):
    d = project_dir()
    data = load(d)
    nodes = all_nodes(data)
    errors, warns = [], []
    srcs = {s["id"]: s for s in data["sources"]}

    def active(n):
        return n.get("status", "active") == "active"

    # ссылки
    for n in nodes.values():
        for ref in n.get("based_on", []) + n.get("sources", []):
            if ref not in nodes:
                errors.append(f"{n['id']}: ссылка на несуществующий {ref}")
            elif active(n) and nodes[ref].get("status") == "revoked":
                errors.append(f"{n['id']}: опирается на отозванный {ref} — пересмотрите")
            elif active(n) and nodes[ref].get("status") == "disputed":
                warns.append(f"{n['id']}: опирается на оспоренный {ref}")
    # утверждения
    for c in data["claims"]:
        if not active(c):
            continue
        real = [s for s in c.get("sources", []) if s in srcs and srcs[s]["kind"] not in ("synthetic", "method")]
        if any(srcs[s]["kind"] == "method" for s in c.get("sources", []) if s in srcs) \
                and c["type"] not in METHOD_ALLOWED:
            errors.append(f"{c['id']}: вывод методологического навыка записан как {c['type']} — должен быть гипотезой")
        if c["type"] == "fact" and not real:
            errors.append(f"{c['id']}: ФАКТ без реального источника")
        if c["type"] == "synthetic" and not c.get("sources"):
            warns.append(f"{c['id']}: синтетика без ссылки на сессию респондента")
        if c["type"] == "inference" and not c.get("based_on"):
            errors.append(f"{c['id']}: ВЫВОД без based_on")
        if c["type"] == "hypothesis" and not c.get("check"):
            warns.append(f"{c['id']}: у гипотезы не указано, как её проверить (--check)")
        if any(srcs[s].get("flag") for s in c.get("sources", []) if s in srcs):
            warns.append(f"{c['id']}: опирается на помеченный источник")

    # опора на опровергнутую гипотезу
    refuted = {c["id"] for c in data["claims"] if active(c)
               and (c.get("verification") or {}).get("result") == "refuted"}
    for n in nodes.values():
        if active(n) and not n["id"].startswith("S"):
            bad = [r for r in n.get("based_on", []) if r in refuted]
            if bad:
                warns.append(f"{n['id']}: опирается на опровергнутую гипотезу {', '.join(bad)} — пересмотрите")
    # свежесть фактов
    cutoff = (dt.date.today() - dt.timedelta(days=STALE_DAYS)).isoformat()
    stale = []
    for c in data["claims"]:
        if active(c) and c["type"] == "fact":
            pubs = [srcs[s].get("published") or "" for s in c.get("sources", [])
                    if s in srcs and srcs[s]["kind"] in ("web", "doc", "table")]
            if pubs and all((not p) or p < cutoff for p in pubs):
                stale.append(c["id"])
    if stale:
        warns.append(f"фактов с источником старше 6 месяцев или без даты: {len(stale)} "
                     f"({', '.join(stale[:10])}{' …' if len(stale) > 10 else ''}) — "
                     "если это текущие цены, состав или условия, перепроверьте")

    # вывод не должен держаться только на синтетике
    def leaf_types(nid, seen=None):
        seen = seen or set()
        if nid in seen or nid not in nodes:
            return set()
        seen.add(nid)
        n = nodes[nid]
        if n["id"].startswith("C") and n["type"] != "inference":
            return {n["type"]}
        out = set()
        for r in n.get("based_on", []):
            out |= leaf_types(r, seen)
        return out
    for k in data["conclusions"] + data["options"]:
        if not active(k):
            continue
        if not k.get("based_on"):
            warns.append(f"{k['id']}: не опирается ни на одно утверждение")
            continue
        lt = leaf_types(k["id"])
        if lt and lt <= {"synthetic"}:
            errors.append(f"{k['id']}: держится только на синтетике — она не доказывает спрос")
        elif lt and lt <= {"synthetic", "hypothesis", "forecast", "opinion"}:
            warns.append(f"{k['id']}: нет ни одного факта в основании")
    # варианты
    opts = [o for o in data["options"] if active(o)]
    if opts:
        kinds = {o["kind"] for o in opts}
        if len(opts) < 3:
            errors.append(f"вариантов {len(opts)}, нужно не меньше 3")
        for kind, name in (("status_quo", "«оставить как есть»"), ("close", "«закрыть направление»")):
            if kind not in kinds:
                errors.append(f"нет варианта {name}")
        for o in opts:
            if not any(x.get("target") == o["id"] and active(x) for x in data["objections"]):
                errors.append(f"{o['id']}: нет сильного возражения")
            solid, total, ratio = strength(data, o["id"])
            direct_h = [r for r in o.get("based_on", []) if r in nodes and nodes[r].get("type") in
                        ("hypothesis", "forecast", "synthetic", "opinion") and active(nodes[r])]
            if total and (ratio < 0.6 or direct_h):
                warns.append(f"{o['id']}: сила оснований {ratio:.0%} (фактов {solid} из {total} опор)"
                             + (f"; напрямую держится на непроверенном: {', '.join(direct_h)}" if direct_h else "")
                             + " — проверить до вложений")
    # стратегия: обещания опираются на продукт
    fids = {f["id"] for f in data["features"] if active(f)}
    for p in data["promises"]:
        if active(p) and not (set(p.get("based_on", [])) & fids):
            errors.append(f"{p['id']}: обещание не опирается ни на один элемент продукта (F)")
    # решения
    for dcs in data["decisions"]:
        if not active(dcs):
            continue
        for fld, name in (("owner", "ответственный"), ("metric", "показатель"), ("review_if", "условие пересмотра")):
            if not dcs.get(fld):
                errors.append(f"{dcs['id']}: не указан {name}")
        if dcs.get("review_date") and dcs["review_date"] <= dt.date.today().isoformat():
            warns.append(f"{dcs['id']}: подошла дата пересмотра ({dcs['review_date']})")

    counts = ", ".join(f"{k}: {len([n for n in data[k] if n.get('status','active')=='active'])}"
                       for k in PREFIX.values())
    print(f"Реестр: {counts}")
    vs = verification_stats(data)
    if vs["total"]:
        print(f"Гипотез и прогнозов проверено: {vs['checked']} из {vs['total']} "
              f"(подтверждено {vs['confirmed']}, опровергнуто {vs['refuted']}, "
              f"частично {vs['partial']}, данных не хватило {vs['inconclusive']})")
    for w in warns:
        print("  ⚠ " + w)
    for e in errors:
        print("  ✗ " + e)
    if not errors:
        print("Проверка пройдена" + (" (есть предупреждения)" if warns else "") + ".")
    sys.exit(1 if errors else 0)  # ошибки — всегда код 1; --strict оставлен для совместимости


def cmd_show(a):
    d = project_dir()
    data = load(d)
    n = all_nodes(data).get(a.id)
    if not n:
        die(f"узел {a.id} не найден")
    print(json.dumps(n, ensure_ascii=False, indent=2))


def cmd_summary(a):
    d = project_dir()
    data = load(d)
    types = {}
    for c in data["claims"]:
        if c["status"] == "active":
            types[c["type"]] = types.get(c["type"], 0) + 1
    rev = sum(1 for k in PREFIX.values() for n in data[k] if n.get("status") == "revoked")
    print(f"Проект: {d.name}. Источников: {len(data['sources'])}. Утверждений по типам: {types or '—'}. "
          f"Выводов: {len([n for n in data['conclusions'] if n.get('status','active')=='active'])}, "
          f"вариантов: {len([n for n in data['options'] if n.get('status','active')=='active'])}, "
          f"решений: {len([n for n in data['decisions'] if n.get('status','active')=='active'])}, "
          f"отозвано: {rev}.")
    vs = verification_stats(data)
    if vs["total"]:
        print(f"Гипотез проверено: {vs['checked']} из {vs['total']} (подтверждено {vs['confirmed']}, "
              f"опровергнуто {vs['refuted']}, частично {vs['partial']}).")


def cmd_report(a):
    """Читаемая таблица доказательств для руководителя продукта: output/evidence.md"""
    d = project_dir()
    data = load(d)
    srcs = {s["id"]: s for s in data["sources"]}
    L = [f"# Доказательная база: {data.get('meta', {}).get('request', d.name)}", "",
         f"_Сформировано {now()} из ledger.json. Не редактируйте вручную._", ""]

    def src_link(sid):
        s = srcs.get(sid)
        if not s:
            return sid
        href = s.get("url") or s.get("file") or ""
        t = f"[{sid}: {s['title']}]({href})" if href else f"{sid}: {s['title']}"
        return t + (" ⚠" if s.get("flag") else "")

    L += ["## Утверждения", "", "| id | метка | утверждение | источники / основания | уверенность | статус |",
          "|---|---|---|---|---|---|"]
    gone = []   # отозванные — в конец документа, свёрнуто: история, а не основание
    for c in data["claims"]:
        if c["status"] == "revoked":
            gone.append(c)
            continue
        refs = ", ".join([src_link(s) for s in c.get("sources", [])] + c.get("based_on", []))
        st = c["status"] + (f" ({c.get('status_reason')})" if c.get("status_reason") else "")
        v = c.get("verification")
        if v:
            vrefs = ", ".join([src_link(x) for x in v.get("sources", [])] + v.get("based_on", []))
            st += f"; проверка: {VERIFY_RESULTS[v['result']]}" + (f" — {v['note']}" if v.get("note") else "") \
                  + (f" [{vrefs}]" if vrefs else "")
        L.append(f"| {c['id']} | {LABEL.get(c['type'], c['type'])} | {c['text']} | {refs} | {c.get('confidence') or ''} | {st} |")
    for key, title in (("conclusions", "Выводы"), ("options", "Варианты"), ("objections", "Возражения"),
                       ("features", "Элементы продукта"), ("promises", "Обещания коммуникации"),
                       ("decisions", "Решения")):
        if not data[key]:
            continue
        L += ["", f"## {title}", ""]
        for n in data[key]:
            if n["status"] == "revoked":
                gone.append(n)
                continue
            extra = ""
            if key == "options":
                extra = f" _({n['kind']})_"
            if key == "objections":
                extra = f" → {n['target']}"
            if key == "decisions":
                extra = (f" — ответственный: {n.get('owner')}, показатель: {n.get('metric')}, "
                         f"пересмотр если: {n.get('review_if')}, дата: {n.get('review_date') or '—'}")
            mark = "~~" if n["status"] == "revoked" else ""
            L.append(f"- **{n['id']}**{extra}: {mark}{n['text']}{mark} ← {', '.join(n.get('based_on', [])) or '—'}")
    if gone:
        L += ["", f"## Отозванные записи ({len(gone)})", "",
              "<details><summary>История: что отозвано и почему — не основание для выводов</summary>", "",
              "| id | было | почему отозвано |", "|---|---|---|"]
        L += [f"| {n['id']} | {(n.get('text') or '')[:160]} | {n.get('status_reason') or ''} |" for n in gone]
        L += ["", "</details>"]
    L += ["", "## Источники", ""]
    for s in data["sources"]:
        L.append(f"- {src_link(s['id'])} — {s['kind']}, опубликовано: {s.get('published') or '?'}, "
                 f"получено: {s['accessed'][:10]}" + (f". Пометка: {s['flag']}" if s.get("flag") else ""))
    out = d / "output" / "evidence.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Записано: {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description="Реестр утверждений проекта")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("new"); p.add_argument("name"); p.add_argument("request"); p.set_defaults(f=cmd_new)
    p = sp.add_parser("use"); p.add_argument("name"); p.set_defaults(f=cmd_use)
    p = sp.add_parser("list"); p.set_defaults(f=cmd_list)

    p = sp.add_parser("add-source")
    p.add_argument("--title", required=True); p.add_argument("--url"); p.add_argument("--file")
    p.add_argument("--kind", required=True); p.add_argument("--published"); p.add_argument("--note")
    p.set_defaults(f=cmd_add_source)

    p = sp.add_parser("source-flag"); p.add_argument("id"); p.add_argument("--reason", required=True)
    p.set_defaults(f=cmd_source_flag)

    p = sp.add_parser("add")
    p.add_argument("prefix", help="C | K | O | X | F | P | D")
    p.add_argument("--text", required=True)
    p.add_argument("--type"); p.add_argument("--sources"); p.add_argument("--based-on")
    p.add_argument("--confidence", choices=["high", "medium", "low"])
    p.add_argument("--check", help="как проверить гипотезу")
    p.add_argument("--kind"); p.add_argument("--target")
    p.add_argument("--owner"); p.add_argument("--metric"); p.add_argument("--review-if"); p.add_argument("--review-date")
    p.add_argument("--force", action="store_true", help="записать, даже если такой текст уже есть")
    p.set_defaults(f=cmd_add)
    p = sp.add_parser("search", help="поиск по словам во всех узлах"); p.add_argument("words", nargs="+")
    p.set_defaults(f=cmd_search)
    p = sp.add_parser("choose", help="зафиксировать выбор руководителя")
    p.add_argument("ids"); p.add_argument("--text", required=True); p.set_defaults(f=cmd_choose)

    p = sp.add_parser("verify", help="итог проверки гипотезы или прогноза")
    p.add_argument("id"); p.add_argument("--result", required=True, choices=list(VERIFY_RESULTS))
    p.add_argument("--sources"); p.add_argument("--based-on"); p.add_argument("--note")
    p.set_defaults(f=cmd_verify)
    p = sp.add_parser("revoke"); p.add_argument("id"); p.add_argument("--reason", required=True)
    p.set_defaults(f=cmd_revoke)
    p = sp.add_parser("supersede", help="заменить устаревшее утверждение свежим, сохранив связи")
    p.add_argument("id"); p.add_argument("--by", required=True); p.add_argument("--reason", required=True)
    p.set_defaults(f=cmd_supersede)
    p = sp.add_parser("dispute"); p.add_argument("id"); p.add_argument("--reason", required=True)
    p.set_defaults(f=lambda a: cmd_revoke(a, "disputed"))
    p = sp.add_parser("impact"); p.add_argument("id"); p.set_defaults(f=cmd_impact)
    p = sp.add_parser("validate"); p.add_argument("--strict", action="store_true"); p.set_defaults(f=cmd_validate)
    p = sp.add_parser("show"); p.add_argument("id"); p.set_defaults(f=cmd_show)
    p = sp.add_parser("summary"); p.set_defaults(f=cmd_summary)
    p = sp.add_parser("report"); p.set_defaults(f=cmd_report)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    import signal
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # вывод в head/less без трассировки
    main()
