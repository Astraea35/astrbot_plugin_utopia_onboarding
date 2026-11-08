from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://mhwtb.shop/"
KB_NAME = "乌托邦新人进服指南（官网）"
SOURCE_PAGES = (
    "index.html",
    "guide-start.html",
    "guide-faq.html",
    "client-mod-list.html",
    "rules.html",
)


def build_documents(pages: dict[str, str]) -> dict[str, dict]:
    """Extract official page sections into source-labelled retrieval chunks.

    Args:
        pages: UTF-8 HTML for the fixed official source pages.

    Returns:
        Documents keyed by their stable official page and section names.

    Raises:
        ValueError: A source page lacks its expected article content.
    """
    documents = {}
    for filename in SOURCE_PAGES:
        soup = BeautifulSoup(pages[filename], "html.parser")
        main = soup.find("main")
        if not main or not main.find("h1"):
            raise ValueError(f"Official article missing: {filename}")
        page_title = main.find("h1").get_text(" ", strip=True)
        sections = main.select("section[id]")
        if not sections:
            raise ValueError(f"Official sections missing: {filename}")
        for section in sections:
            if filename == "index.html" and section["id"] not in {"home", "connect"}:
                continue
            heading = section.find(["h1", "h2", "h3"])
            title = heading.get_text(" ", strip=True) if heading else page_title
            url = urljoin(BASE_URL, filename) + "#" + section["id"]
            for item in section.select("script,style,svg,nav"):
                item.decompose()
            for anchor in section.select("a[href]"):
                href = anchor["href"].strip()
                label = anchor.get_text(" ", strip=True)
                if (
                    href
                    and "{{" not in href
                    and urljoin(BASE_URL, href).startswith("https://")
                ):
                    anchor.replace_with(f"{label}（{urljoin(BASE_URL, href)}）")
                else:
                    anchor.replace_with(label)
            for image in section.select("img[alt]"):
                image.replace_with(f"【官网配图：{image['alt']}；详见原文】")
            for code in section.select("code"):
                code.replace_with(code.get_text())
            text = re.sub(r"\s+", " ", section.get_text(" ", strip=True)).strip()
            if not text:
                raise ValueError(f"Empty official section: {url}")
            prefix = f"官网原文：{url}\n主题：{page_title} / {title}\n"
            # Repeat provenance on every chunk, including a split login guide.
            chunks = [
                prefix + text[offset : offset + 900]
                for offset in range(0, len(text), 800)
            ]
            name = f"官网_{filename.removesuffix('.html')}_{section['id']}.txt"
            documents[name] = {
                "source_url": url,
                "title": title,
                "chunks": chunks,
                "sha256": hashlib.sha256("\n".join(chunks).encode("utf-8")).hexdigest(),
            }
    return documents
