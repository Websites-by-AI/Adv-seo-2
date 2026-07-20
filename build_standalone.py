#!/usr/bin/env python3
"""Build a preview-safe, single-file index.html from modular source assets."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / "index.source.html").read_text(encoding="utf-8")
css = "\n".join([
    (ROOT / "static/styles.css").read_text(encoding="utf-8"),
    (ROOT / "static/mobile-fixes.css").read_text(encoding="utf-8"),
    (ROOT / "static/discovery.css").read_text(encoding="utf-8"),
    (ROOT / "static/content-studio.css").read_text(encoding="utf-8"),
    (ROOT / "static/ai-seo.css").read_text(encoding="utf-8"),
    (ROOT / "static/audit-enhanced.css").read_text(encoding="utf-8"),
    (ROOT / "static/vendor-ranking.css").read_text(encoding="utf-8"),
    (ROOT / "static/exhibition.css").read_text(encoding="utf-8"),
])
js = (ROOT / "static/app.js").read_text(encoding="utf-8")
# Raw inline scripts are the most compatible option for file://, workspace previews,
# Vercel static hosting and Docker. Escape a possible closing script sequence.
js = js.replace("</script", "<\\/script")

source = source.replace(
    '<link rel="stylesheet" href="static/styles.css">\n<link rel="stylesheet" href="static/mobile-fixes.css">\n<link rel="stylesheet" href="static/discovery.css">\n<link rel="stylesheet" href="static/content-studio.css">\n<link rel="stylesheet" href="static/ai-seo.css">\n<link rel="stylesheet" href="static/audit-enhanced.css">\n<link rel="stylesheet" href="static/vendor-ranking.css">\n<link rel="stylesheet" href="static/exhibition.css">',
    f"<style>\n{css}\n</style>",
)
source = source.replace(
    '<script src="static/app.js" defer></script>',
    f'<script>\n{js}\n</script>',
)

if 'static/app.js' in source or 'static/styles.css' in source:
    raise SystemExit("Asset replacement failed")
if source.count("<script>") != 1 or source.count("</script>") != 1:
    raise SystemExit("Unexpected script structure in standalone build")
if "function printProposal" not in source:
    raise SystemExit("Application JavaScript was not embedded")

(ROOT / "app.html").write_text(source, encoding="utf-8")
public = ROOT / "public"
public.mkdir(exist_ok=True)
(public / "index.html").write_text(source, encoding="utf-8")
print(f"Built app.html and public/index.html: {len(source):,} characters")
