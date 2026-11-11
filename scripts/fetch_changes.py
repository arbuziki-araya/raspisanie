"""Скачивает файлы замен с сайта колледжа и сохраняет замены группы в changes.json.
Запускается автоматически GitHub Actions (см. .github/workflows/update.yml)."""
import datetime as dt
import io
import json
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

from docx import Document

BASE = "http://smolapo.ru/sites/default/files/Studentam/2026-2027/"
FILES = {"today": "izm1.docx", "tomorrow": "izm2.docx"}
GROUP_RE = re.compile(r"(?<!\d)6\s*1\s*2\s*[-–—]?\s*Б", re.I)
LABEL_RE = re.compile(r"^\d{3}[А-ЯЁ]{1,4}$")
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
TZ = ZoneInfo("Europe/Moscow")


def norm(s):
    return re.sub(r"[\s\-–—.]", "", s).upper().replace("B", "Б")


def is_label(t):
    return bool(LABEL_RE.match(norm(t)))


def is_ours(t):
    return bool(GROUP_RE.search(t.replace("B", "Б")))


def pairs_of(t):
    t = t.strip()
    m = re.match(r"^(\d)\s*[-–]\s*(\d)", t)
    if m:
        return list(range(int(m[1]), int(m[2]) + 1))
    return [int(x) for x in re.findall(r"(?<!\d)([1-7])(?!\d)", t)] if re.match(r"^[\d\s,;\-–]*(пара|п\.?)?\s*$", t, re.I) and t else []


def find_date(text):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
    if m:
        y = int(m[3]); y += 2000 if y < 100 else 0
        return dt.date(y, int(m[2]), int(m[1]))
    m = re.search(r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(\d{4}))?", text, re.I)
    if m:
        y = int(m[3]) if m[3] else dt.datetime.now(TZ).year
        return dt.date(y, MONTHS.index(m[2].lower()) + 1, int(m[1]))
    return None


def dedupe(texts):
    out = []
    for t in texts:
        if not out or out[-1] != t:
            out.append(t)
    return out


def parse(doc):
    entries = []
    for table in doc.tables:
        header, cur = None, None
        for row in table.rows:
            texts = [c.text.strip() for c in row.cells]
            labels = {i: norm(t) for i, t in enumerate(texts) if is_label(t)}
            if len(set(labels.values())) >= 2:          # группы идут столбцами
                header = labels
                continue
            if header:
                first = min(header)
                pair = next((pairs_of(t) for t in texts[:first] if pairs_of(t)), [])
                for i, g in header.items():
                    if g == "612Б" and i < len(texts) and texts[i]:
                        entries.append({"pairs": pair, "text": texts[i]})
                continue
            # группы идут строками
            for t in texts:
                if is_ours(t):
                    cur = "ours"; break
                if is_label(t):
                    cur = None; break
            if cur != "ours":
                continue
            rest = [t for t in dedupe(texts) if t and not is_ours(t)]
            pair = next((pairs_of(t) for t in rest if pairs_of(t)), [])
            rest = [t for t in rest if not pairs_of(t)]
            if rest:
                entries.append({"pairs": pair, "text": " | ".join(rest)})
    if not entries:                                     # замены текстом, без таблицы
        for p in doc.paragraphs:
            if is_ours(p.text):
                entries.append({"pairs": [], "text": p.text.strip()})
    return entries


def load_previous():
    """Прошлый changes.json: если сайт колледжа недоступен, оставляем из него последние удачные данные."""
    try:
        with open("changes.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    now = dt.datetime.now(TZ)
    prev = load_previous()
    result = {"updated": now.isoformat(timespec="minutes"), "files": {}}
    for key, name in FILES.items():
        url = BASE + name
        info = {"url": url, "ok": False, "date": None, "entries": []}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=60).read()
            doc = Document(io.BytesIO(data))
            head = "\n".join(p.text for p in doc.paragraphs[:15])
            if doc.tables:
                head += "\n" + "\n".join(c.text for r in doc.tables[0].rows[:3] for c in r.cells)
            d = find_date(head) or (now.date() + dt.timedelta(days=1 if key == "tomorrow" else 0))
            info.update(ok=True, date=d.isoformat(), entries=parse(doc))
        except Exception as e:  # сайт недоступен или файл другого формата
            old = (prev.get("files") or {}).get(key) or {}
            if old.get("ok"):   # не затираем прошлые замены пустыми данными
                info = {**old, "stale": True}
            info["error"] = str(e)[:200]
        result["files"][key] = info
    if not any(i["ok"] and not i.get("stale") for i in result["files"].values()):
        result["updated"] = prev.get("updated", result["updated"])   # свежих данных нет — время не обновляем
    with open("changes.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
