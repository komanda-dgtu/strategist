#!/usr/bin/env python3
"""Сравнение разметки: дешёвая модель, основная модель, каскад по уверенности — против человека и судьи.

    python3 bench/cascade/score.py --project cascade-bench \
        --models cheap=grok-4.6-high-fast,main=grok-4.7-high-fast,judge=claude-opus-5.5

Нужны файлы в bench/cascade/data/: split.json, gold_sheet.csv (заполненный человеком),
labels_cheap.jsonl, labels_main.jsonl, labels_judge.jsonl. Токены берутся из учёта проекта
(projects/<project>/costs/cursor-turns.jsonl) по имени модели.

Логика (по курсу «Decision Models», AI-мастерская GoPractice, своими словами):
1) судью проверяем на человеке (30 отзывов) — только потом считаем его эталоном для остальных;
2) порог уверенности каскада подбираем на обучающей выборке, а качество меряем на тестовой;
3) сравниваем два числа: качество и токены на 1000 отзывов.
"""
import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
ROOT = HERE.parent.parent
QS = ("q1", "q2", "q3")
NAMES = {"q1": "навязанное (да/нет)", "q2": "уход (да/нет)", "q3": "главная тема (5 вариантов)"}
THRESHOLDS = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]


def norm(v):
    return str(v or "").strip().lower().replace("ё", "е")


def load_labels(name):
    f = D / f"labels_{name}.jsonl"
    if not f.exists():
        return None
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("{"):
            x = json.loads(line)
            out[int(x["id"])] = x
    return out


def acc(pred, truth, ids, q):
    pairs = [(norm(pred[i].get(q)), norm(truth[i].get(q))) for i in ids if i in pred and i in truth and norm(truth[i].get(q))]
    return (sum(a == b for a, b in pairs) / len(pairs), len(pairs)) if pairs else (None, 0)


def cascade(cheap, main, ids, q, t):
    """Ответ дешёвой модели, если её уверенность ≥ t, иначе — основной. Возвращает разметку и долю переданных."""
    out, sent = {}, 0
    for i in ids:
        if i not in cheap or i not in main:
            continue
        conf = float(cheap[i].get(f"{q}_conf") or 0)
        if conf >= t:
            out[i] = {q: cheap[i].get(q)}
        else:
            out[i] = {q: main[i].get(q)}
            sent += 1
    return out, (sent / len(out) if out else 0)


def tokens_by_model(project, skip_gen=()):
    d = ROOT / "projects" / project / "costs"
    f = d / "cursor-turns.jsonl"
    if not f.exists():
        return {}
    excluded = set()
    m = d / "manual.json"
    if m.exists():
        excluded = {r.get("conversation") for r in json.loads(m.read_text(encoding="utf-8")) if r.get("kind") == "exclude"}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        if t.get("conversation_id") in excluded or t.get("generation_id") in skip_gen:
            continue
        out[t["model"]] = out.get(t["model"], 0) + t["input"] + t["output"]   # чтение из кэша уже внутри входа
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="cascade-bench")
    ap.add_argument("--models", default="cheap=grok-4.6-high-fast,main=grok-4.7-high-fast,judge=claude-opus-5.5")
    ap.add_argument("--skip-gen", default="", help="id ответов агента, которые не считать (неудачный прогон), через запятую")
    ap.add_argument("--usd", default="", help="стоимость чатов по панели Usage: cheap=0.12,main=0.40,judge=1.10")
    a = ap.parse_args()
    models = dict(kv.split("=", 1) for kv in a.models.split(","))
    split = json.loads((D / "split.json").read_text(encoding="utf-8"))
    n_all = sum(len(v) for v in split.values())
    human = {}
    with open(D / "gold_sheet.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            human[int(r["id"])] = r
    labs = {k: load_labels(k) for k in ("cheap", "main", "judge")}
    missing = [k for k, v in labs.items() if v is None]
    if missing:
        raise SystemExit(f"Нет разметки: {', '.join('labels_' + k + '.jsonl' for k in missing)}")
    judge, cheap, mainm = labs["judge"], labs["cheap"], labs["main"]

    L = ["# Каскад по уверенности: дешёвая модель → основная", "",
         f"Отзывов: {n_all} (эталон человека {len(split['gold'])}, обучающая {len(split['train'])}, "
         f"тестовая {len(split['test'])}). Модели: " + ", ".join(f"{k} — `{v}`" for k, v in models.items()) + ".", ""]

    L += ["## 1. Насколько верна каждая модель на ручном эталоне (30 отзывов)", "",
          "| Вопрос | Дешёвая | Основная | Судья |", "|---|---|---|---|"]
    for q in QS:
        cells = []
        for k in ("cheap", "main", "judge"):
            v, n = acc(labs[k], human, split["gold"], q)
            cells.append("—" if v is None else f"{v:.0%} ({n})")
        L.append(f"| {NAMES[q]} | " + " | ".join(cells) + " |")
    L += ["", "Судья становится эталоном для остальных отзывов, только если на ручном эталоне он близок к человеку.", ""]

    L += ["## 2. Тестовая выборка: качество против судьи и доля, переданная основной модели", "",
          "| Вопрос | Дешёвая | Основная | Каскад | Порог (подобран на обучающей) | Передано основной |",
          "|---|---|---|---|---|---|"]
    shares = []
    for q in QS:
        ac, _ = acc(cheap, judge, split["test"], q)
        am, _ = acc(mainm, judge, split["test"], q)
        # порог: самый низкий, при котором каскад на обучающей не хуже основной больше чем на 2 п.п.
        best = None
        am_train, _ = acc(mainm, judge, split["train"], q)
        for t in THRESHOLDS:
            lab, share = cascade(cheap, mainm, split["train"], q, t)
            a_t, _ = acc(lab, judge, split["train"], q)
            if a_t is not None and am_train is not None and a_t >= am_train - 0.02:
                best = t
                break
        best = best or THRESHOLDS[-1]
        lab, share = cascade(cheap, mainm, split["test"], q, best)
        acs, _ = acc(lab, judge, split["test"], q)
        shares.append(share)
        f = lambda v: "—" if v is None else f"{v:.0%}"
        L.append(f"| {NAMES[q]} | {f(ac)} | {f(am)} | {f(acs)} | {best} | {share:.0%} |")

    L += ["", "**Как меняется каскад с порогом (тестовая выборка, против судьи)**", "",
          "| Порог уверенности дешёвой модели | " + " | ".join(NAMES[q] for q in QS) + " |",
          "|---|" + "---|" * len(QS)]
    for t in THRESHOLDS:
        cells = []
        for q in QS:
            lab, share = cascade(cheap, mainm, split["test"], q, t)
            v, _ = acc(lab, judge, split["test"], q)
            cells.append(f"{v:.0%}, основной {share:.0%}")
        L.append(f"| {t} | " + " | ".join(cells) + " |")
    L += ["", "**Говорит ли уверенность дешёвой модели что-то о точности** (обучающая и тестовая вместе, против судьи)", "",
          "| Уверенность | " + " | ".join(NAMES[q] for q in QS) + " |", "|---|" + "---|" * len(QS)]
    ids_all = split["train"] + split["test"]
    for lo, hi in ((0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.01)):
        cells = []
        for q in QS:
            sub = [i for i in ids_all if i in cheap and lo <= float(cheap[i].get(f"{q}_conf") or 0) < hi]
            v, n = acc(cheap, judge, sub, q)
            cells.append("—" if v is None else f"{v:.0%} ({n})")
        L.append(f"| {lo}–{min(hi, 1.0)} | " + " | ".join(cells) + " |")

    tok = tokens_by_model(a.project, set(filter(None, a.skip_gen.split(","))))
    tc, tm, tj = (tok.get(models.get(k), 0) for k in ("cheap", "main", "judge"))
    L += ["", "## 3. Цена: токены на 1000 отзывов", ""]
    if tc and tm:
        per = lambda x: round(x / n_all * 1000)
        share = sum(shares) / len(shares)
        tcas = tc + tm * share
        L += ["| Пайплайн | Токенов на 1000 отзывов |", "|---|---|",
              f"| Дешёвая модель | {per(tc):,} |", f"| Основная модель | {per(tm):,} |",
              f"| Каскад (дешёвая на всё + основная на {share:.0%} сомнительных) | {per(tcas):,} |"]
        if tj:
            L.append(f"| Судья (разметка эталона) | {per(tj):,} |")
        if a.usd:
            usd = {k: float(v) for k, v in (kv.split("=", 1) for kv in a.usd.split(","))}
            if "cheap" in usd and "main" in usd:
                pu = lambda x: f"${x / n_all * 1000:.2f}"
                L += ["", "| Пайплайн | $ на 1000 отзывов (по панели Usage) |", "|---|---|",
                      f"| Дешёвая модель | {pu(usd['cheap'])} |", f"| Основная модель | {pu(usd['main'])} |",
                      f"| Каскад | {pu(usd['cheap'] + usd['main'] * share)} |"]
        L += ["", "Токены = вход + выход по хуку `stop` (совпадает с панелью Usage Cursor); при подписке они входят в её цену. "
                  "Каскад посчитан как прогон дешёвой модели на всех отзывах плюс доля основной."]
    else:
        L.append(f"_Токенов по моделям не найдено в учёте проекта `{a.project}` — проверьте, что разметка шла в нём._")
    L += ["", "## Как читать", "",
          "- Если каскад почти так же точен, как основная модель, а токенов заметно меньше, — массовую разметку "
          "агент отдаёт дешёвой модели, сомнительные решения — основной (AGENTS.md, «Маршрутизация»).",
          "- Уверенность здесь называет сама модель словами, это не вероятность, как у специализированных моделей вроде Jev. "
          "Поэтому порог подбирается на обучающей выборке, а проверяется на тестовой.", ""]
    (HERE / "result.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
