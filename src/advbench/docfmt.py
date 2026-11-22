"""Compose corpus-style document text and shared generation guidance."""
from __future__ import annotations
import re

STYLE_GUIDE = """Corpus style (BrowseComp-Plus is a crawl of real web pages converted to text):
- Each page is plain text, sometimes with leftover navigation or boilerplate lines ("Skip to content", "Home | About | Contact", "Share this:", "Related posts"), bylines, timestamps, or infobox-style "key: value" lines for wiki pages.
- The body usually starts by repeating the page title on its own line.
- Write like the real outlet would: a local news article, a university or club web page, a Wikipedia-style article, a blog post, an obituary, a forum thread, a catalogue record, a press release. No markdown headings with '#', no bullet lists unless the page type would have them.
- Never mention that the page is fictional, generated, a decoy, or part of a benchmark; never use the words fictional, invented or hypothetical.
- Real pages carry ordinary detail beyond the facts that matter here (history, people, quotes, logistics, side stories); do not mirror the question's structure or order, and no keyword stuffing in titles.
- Use names that fit the country, era and domain (local naming conventions for people, institutions, clubs, outlets, streets). Avoid generic placeholder names such as "Western Plains University", "Harbourside", "Meridian", "Lantern", "Riverside".
- State facts positively; never contrast them with alternatives the page has no reason to mention ("in 1999, not the 2000s", "rather than", "unlike")."""


def compose(title: str, body: str, date: str | None = None, author: str | None = None) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    fm = ["---", f"title: {title}"]
    if author:
        author = re.sub(r"\s+", " ", author).strip()
        fm.append(f"author: {author}")
    if date:
        fm.append(f"date: {date.strip()}")
    fm.append("---")
    return "\n".join(fm) + "\n" + body.strip() + "\n"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def alias_hits(text: str, aliases: list[str]) -> list[str]:
    """Aliases (>=4 chars, not purely numeric) that appear as whole words in text."""
    t = " " + norm(text) + " "
    hits = []
    for a in aliases:
        na = norm(a)
        if len(na) < 4 or na.replace(" ", "").isdigit():
            continue
        if f" {na} " in t:
            hits.append(a)
    return hits
