#!/usr/bin/env python3
"""Lists favorite thread links of user and saves them as .md.
"""
from bs4 import BeautifulSoup
import os
import logging
import re
import requests
import tempfile
import time

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)

BASE_URL = "https://news.ycombinator.com"

if "HN_USER" in os.environ:
    USER = os.environ["HN_USER"]
else:
    logging.info("HN_USER environment variable not set, using default USER.")
    USER = os.environ["USER"]

LINK_LIMIT = 10

CONTEXT_PROMPT = """
## Context

The following is a Hacker News thread in markdown format. The comments discuss a
certain link, of which the content (besides the title) is not included here. The
comments are indented according to the level of the comment, with the top-level
comment being unindented.
"""


def user_exists(soup) -> bool:
    return soup.text != "No such user."


def get_item_links_from_page(url) -> (list[str], None | str):
    logging.info(f"Fetching page: {url}")
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    if not user_exists(soup):
        raise ValueError(f"Specify valid user instead of '{USER}'")

    pattern = re.compile(r"^/?item\?id=\d+$")
    links = {
        BASE_URL + "/" + a["href"].lstrip("/") for a in soup.find_all("a", href=pattern)
    }
    logging.info(f"  Found {len(links)} HN item links on this page.")

    more_link = soup.find("a", string="More")
    next_page = BASE_URL + "/" + more_link["href"] if more_link else None
    if next_page:
        logging.info(f"  Next page: {next_page}")
    else:
        logging.info("  No more pages found.")

    return links, next_page


def retrieve_user_favorite_links(user=USER, limit=LINK_LIMIT) -> list[str]:
    url = f"{BASE_URL}/favorites?id={user}"
    all_links = []
    page_count = 0

    while url:
        page_count += 1
        logging.info(f"--- Processing page {page_count} ---")
        links, url = get_item_links_from_page(url)
        before_count = len(all_links)
        all_links.extend(links)
        logging.info(
            f"  Total unique links so far: {len(all_links)} (+{len(all_links) - before_count})"
        )
        if len(all_links) >= limit:
            logging.info(f"  Reached limit of {limit} links, stopping.")
            all_links = all_links[:limit]
            break

    with tempfile.NamedTemporaryFile(
        prefix="hn_comment_urls_",
        suffix=".txt",
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as tmpfile:
        for link in all_links:
            tmpfile.write(link + "\n")

        print(tmpfile.name)

    logging.info(f"Found {len(all_links)} total unique HN item links.")
    return all_links


def fetch_hn_thread_markdown(url) -> (str, str):
    res = requests.get(url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    if title := soup.find("title"):
        title_text = title.text
    else:
        logging.error(f"Could not find title in {url}")
        title_text = f"hn_{url.split('=')[-1]}"

    comments = []
    comment_rows = soup.find_all("tr", class_="athing comtr")

    for row in comment_rows:
        cid = row["id"]
        indent_td = row.find("td", class_="ind")
        indent_px = int(indent_td.img["width"]) if indent_td and indent_td.img else 0
        indent_level = indent_px // 40

        author = row.find("a", class_="hnuser")
        author_text = author.text if author else "[deleted]"

        commtext_td = row.find("div", class_="comment")
        # Remove "reply" links, scripts etc
        for tag in commtext_td.find_all(["div", "span"], class_=["reply", "unvoted"]):
            tag.decompose()
        comment_html = commtext_td.get_text("\n").strip()

        comments.append((indent_level, author_text, comment_html))

    md_lines = [f"# {title_text}\n\n"]

    md_lines.append(CONTEXT_PROMPT.strip() + "\n\n")

    md_lines.append("## Comments\n\n")

    for indent, author, comment in comments:
        indent_str = "  " * indent
        md_lines.append(f"{indent_str}- **{author}**:\n")
        comment_lines = comment.splitlines()
        for line in comment_lines:
            md_lines.append(f"{indent_str}  {line}")
        md_lines.append("")

    return title_text, "\n".join(md_lines)


def main():
    links = retrieve_user_favorite_links()
    with tempfile.TemporaryDirectory(
        prefix=f"hn_threads_md_{time.time()}_", delete=False
    ) as tmpdir:
        for link in links:
            title, md = fetch_hn_thread_markdown(link)
            with open(f"{tmpdir}/{title}.md", "w", encoding="utf-8") as f:
                f.write(md)
                logging.info(f"Saved markdown for {title} to {f.name}")


if __name__ == "__main__":
    main()
