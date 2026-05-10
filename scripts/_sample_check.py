import re
from pathlib import Path

wiki = Path("wiki")
count = 0
for p in sorted(wiki.glob("*.md")):
    if p.name == "index.md":
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    title   = re.search(r"^title:\s*(.+)$",  text, re.MULTILINE)
    authors = re.search(r"^authors:\s*(.+)$", text, re.MULTILINE)
    year    = re.search(r"^year:\s*(.+)$",    text, re.MULTILINE)
    source  = re.search(r"Source: `(.+?)`",   text)
    print(f"FILE:    {p.name}")
    print(f"title:   {title.group(1)[:70] if title else '?'}")
    print(f"authors: {authors.group(1)[:70] if authors else '?'}")
    print(f"year:    {year.group(1) if year else '?'}")
    print(f"source:  {source.group(1) if source else '?'}")
    print()
    count += 1
    if count >= 8:
        break
