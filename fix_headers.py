import pathlib

OLD = "# ARIS \u2014 Automated Regulatory Intelligence System"
NEW = "# ARIS - Automated Regulatory Intelligence System"

updated = 0
for p in pathlib.Path(".").rglob("*.py"):
    if "node_modules" in str(p) or "__pycache__" in str(p):
        continue
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
        if OLD in src or "\x97" in src or "\u2014" in src:
            # Fix em dash however it appears
            src = src.replace(OLD, NEW)
            src = src.replace("\u2014", "-")  # em dash
            src = src.replace("\x97", "-")  # Windows-1252 em dash
            p.write_text(src, encoding="utf-8")
            print(f"  fixed: {p}")
            updated += 1
    except Exception as e:
        print(f"  skip {p}: {e}")

print(f"\nFixed {updated} files")
