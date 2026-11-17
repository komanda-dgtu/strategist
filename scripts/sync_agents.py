#!/usr/bin/env python3
"""
Один источник правды для субагентов: .claude/agents/*.md.
Этот скрипт пересобирает их копии в формате Cursor (.cursor/agents/*.md):
поля name, description, model, readonly: true. Модель для Cursor — из поля `cursor-model`
исходника (если его нет — inherit, модель основного чата). Запускайте после правки субагентов.

  python3 scripts/sync_agents.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".claude" / "agents", ROOT / ".cursor" / "agents"


def main():
    DST.mkdir(parents=True, exist_ok=True)
    for f in sorted(SRC.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not m:
            continue
        head, body = m.groups()
        fields = dict(re.findall(r"^(\w[\w-]*):\s*(.*)$", head, re.M))
        out = ("---\n"
               f"name: {fields.get('name', f.stem)}\n"
               f"description: {fields.get('description', '')}\n"
               f"model: {fields.get('cursor-model', 'inherit')}\n"
               "readonly: true\n"
               "---\n"
               "<!-- Сгенерировано scripts/sync_agents.py из .claude/agents. Правьте исходник. -->\n" + body)
        (DST / f.name).write_text(out, encoding="utf-8")
        print(f"{f.name} → .cursor/agents/{f.name}")


if __name__ == "__main__":
    main()
