#!/usr/bin/env python3
"""
Хук начала сессии: передаёт агенту состояние активного проекта, чтобы продолжить после перерыва.

  Claude Code:  python3 hooks/session_start.py           (печатает текст — он попадает в контекст)
  Cursor:       python3 hooks/session_start.py --cursor  (печатает JSON с additional_context)
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
active = ROOT / ".active_project"


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


def build():
    name = active.read_text(encoding="utf-8").strip() if active.exists() else _fallback_project(ROOT / "projects")
    if not name:
        return ("Активного проекта нет. Если пользователь пришёл с продуктовым запросом — "
                "начни с навыка /start (AGENTS.md).")
    parts = [f"=== Продолжение работы. Активный проект: {name} ==="]
    state = ROOT / "projects" / name / "state.md"
    if state.exists():
        parts.append(state.read_text(encoding="utf-8"))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "ledger.py"), "summary"],
                       capture_output=True, text=True, cwd=ROOT)
    parts.append(r.stdout or r.stderr)
    passport = ROOT / "projects" / name / "output" / "00-passport.md"
    if passport.exists():
        parts.append("Паспорт решения: projects/%s/output/00-passport.md" % name)
    parts.append("Правило: не повторяй выполненные шаги; шаг «в работе» сначала проверь по файлам и реестру. "
                 "Коротко напомни пользователю, где остановились, что изменилось и что предлагаешь дальше; "
                 "спроси, продолжать ли.")
    return "\n".join(parts)


def _mark(source):
    """Отметка в журнале проекта: хук начала сессии действительно сработал (для проверки в Cursor)."""
    try:
        name = active.read_text(encoding="utf-8").strip() if active.exists() else _fallback_project(ROOT / "projects")
        if name:
            import datetime as dt
            log = ROOT / "projects" / name / "costs" / "sessions.log"
            log.parent.mkdir(exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} session_start {source}\n")
    except Exception:
        pass


def _just_ran(seconds=30):
    """Cursor запускает и свой хук, и хук из настроек Claude Code. Второй вызов подряд ничего не добавляет."""
    try:
        import datetime as dt
        name = active.read_text(encoding="utf-8").strip() if active.exists() else _fallback_project(ROOT / "projects")
        log = ROOT / "projects" / name / "costs" / "sessions.log"
        last = log.read_text(encoding="utf-8").strip().splitlines()[-1].split()[0]
        return 0 <= (dt.datetime.now() - dt.datetime.fromisoformat(last)).total_seconds() < seconds
    except Exception:
        return False


if __name__ == "__main__":
    if _just_ran():
        print("{}" if "--cursor" in sys.argv else "")
        sys.exit(0)
    text = build()
    _mark("cursor" if "--cursor" in sys.argv else "claude")
    if "--cursor" in sys.argv:
        try:
            sys.stdin.read()  # Cursor передаёт JSON события; он нам не нужен
        except Exception:
            pass
        print(json.dumps({"additional_context": text}, ensure_ascii=False))
    else:
        print(text)
