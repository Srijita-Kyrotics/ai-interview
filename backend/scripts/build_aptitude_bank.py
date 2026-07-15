"""
Aptitude Question Bank Scraper with Image Support
Scrapes aptitude questions from IndiaBix and other sources, downloads images,
and outputs to frontend/public/questions/aptitude.json format.
"""

from __future__ import annotations

import json
import os
import re
import time
import hashlib
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_QUESTIONS_DIR = BASE_DIR / "frontend" / "public" / "questions"
IMAGE_DIR = FRONTEND_QUESTIONS_DIR / "images"
OUTPUT_JSON = FRONTEND_QUESTIONS_DIR / "aptitude.json"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

SESSION = requests.Session()
SESSION.headers.update(REQUEST_HEADERS)

QUESTION_ID_COUNTER: dict[str, int] = {}


def _next_id(section: str) -> str:
    QUESTION_ID_COUNTER.setdefault(section, 0)
    QUESTION_ID_COUNTER[section] += 1
    return f"{section}-{QUESTION_ID_COUNTER[section]:04d}"


def download_image(img_url: str, page_url: str) -> str | None:
    """Download an image to IMAGE_DIR. Returns relative path or None.
    Uses content hash for deduplication."""
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        abs_url = urljoin(page_url, img_url)
        resp = SESSION.get(abs_url, timeout=15)
        resp.raise_for_status()

        parsed = urlparse(abs_url)
        ext = os.path.splitext(parsed.path)[1] or ".png"
        content_hash = hashlib.md5(resp.content).hexdigest()
        filename = f"{content_hash}{ext}"
        dest = IMAGE_DIR / filename
        if not dest.exists():
            dest.write_bytes(resp.content)
        return f"/questions/images/{filename}"
    except Exception as e:
        print(f"  [WARN] Failed to download {img_url}: {e}")
        return None


def extract_images_from_html(html_element, page_url: str) -> list[str]:
    """Extract and download images from an HTML element. Returns list of relative paths.
    Also records original URL references for images that couldn't be downloaded."""
    paths: list[str] = []
    if html_element is None:
        return paths
    for img_tag in html_element.find_all("img"):
        src = img_tag.get("src")
        if not src:
            continue
        # Skip math/formula images (small GIFs used for notation)
        if re.search(r'/aptitude/1-sym-|/data-interpretation/common/\d+-sym-', src):
            continue
        local_path = download_image(src, page_url)
        if local_path:
            paths.append(local_path)
        else:
            # Store original URL as reference when download fails
            abs_url = urljoin(page_url, src)
            paths.append(abs_url)
    return paths


# Unicode superscript/subscript maps for math notation
SUP_MAP = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '(': '⁽', ')': '⁾', '.': '·',
}

SUB_MAP = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
}


# Mapping for IndiaBix math symbol images
MATH_SYMBOL_IMAGES = {
    '1-sym-tfr.gif': '/',          # fraction bar (horizontal line)
    '1-sym-imp.gif': '=>',         # implies (arrow)
    '1-sym-oparen-h1.gif': '(',    # open parenthesis (large)
    '1-sym-cparen-h1.gif': ')',    # close parenthesis (large)
    '1-sym-bim.gif': 'x',          # multiplication sign
    '1-sym-cbrace-h2.gif': '}',    # closing curly brace
    '1-sym-neq.gif': '!=',         # not equal
}


def convert_math_images(element) -> None:
    """Replace IndiaBix math symbol <img> tags with text equivalents."""
    for img in element.find_all('img'):
        src = img.get('src', '')
        name = src.split('/')[-1]
        if name in MATH_SYMBOL_IMAGES:
            img.replace_with(MATH_SYMBOL_IMAGES[name])


def convert_math_notation(element) -> None:
    """Replace <sup>/<sub> tags in-place with Unicode math notation."""
    for tag in element.find_all(['sup', 'sub']):
        tag_name = tag.name
        inner = tag.get_text()
        if tag_name == 'sup':
            if re.match(r'^[\d.+\-]+$', inner):
                repl = ''.join(SUP_MAP.get(c, c) for c in inner)
            else:
                repl = f'^({inner})'
        else:
            if re.match(r'^\d+$', inner):
                repl = ''.join(SUB_MAP.get(c, c) for c in inner)
            else:
                repl = f'_({inner})'
        tag.replace_with(repl)


def convert_fraction_tables(element) -> None:
    """Convert IndiaBix fraction tables (ga-tbl-answer) to inline (num)/(den) notation."""
    for table in element.find_all('table', class_='ga-tbl-answer'):
        rows = table.find_all('tr')
        if len(rows) < 2:
            # Single-row table: just get text
            table.replace_with(table.get_text(' ', strip=True))
            continue

        num_cells = rows[0].find_all('td')
        den_cells = rows[1].find_all('td')

        parts = []
        den_idx = 0
        for cell in num_cells:
            if cell.get('rowspan'):
                # Shared cell spanning both rows (e.g. "If", "=", "+")
                text = cell.get_text(' ', strip=True)
                if text:
                    parts.append(text)
            else:
                # Numerator cell: pair with corresponding denominator cell
                num_text = cell.get_text(' ', strip=True)
                den_text = ''
                if den_idx < len(den_cells):
                    den_text = den_cells[den_idx].get_text(' ', strip=True)
                    den_idx += 1
                if num_text or den_text:
                    parts.append(f'({num_text})/({den_text})' if den_text else num_text)

        # Any remaining denominator cells (rowspan cells in denominator only)
        while den_idx < len(den_cells):
            if den_cells[den_idx].get('rowspan'):
                text = den_cells[den_idx].get_text(' ', strip=True)
                if text:
                    parts.append(text)
            den_idx += 1

        replacement = ' '.join(parts)
        table.replace_with(replacement)


def convert_mathml(element) -> None:
    """Convert common MathML structures to inline text before extraction."""
    for math in element.find_all('math'):
        replacement = math
        for frac in replacement.find_all('mfrac'):
            children = [child for child in frac.find_all(recursive=False)]
            if len(children) >= 2:
                num = children[0].get_text(' ', strip=True)
                den = children[1].get_text(' ', strip=True)
                frac.replace_with(f'({num})/({den})' if num or den else '')
        for sup in replacement.find_all('msup'):
            children = [child for child in sup.find_all(recursive=False)]
            if len(children) >= 2:
                base = children[0].get_text(' ', strip=True)
                exp = children[1].get_text(' ', strip=True)
                sup.replace_with(f'{base}^({exp})' if exp else base)
        for sub in replacement.find_all('msub'):
            children = [child for child in sub.find_all(recursive=False)]
            if len(children) >= 2:
                base = children[0].get_text(' ', strip=True)
                idx = children[1].get_text(' ', strip=True)
                sub.replace_with(f'{base}_({idx})' if idx else base)


def convert_ordered_lists(element) -> None:
    """Convert <ol><li> elements to numbered text (1. ..., 2. ..., etc.) in-place."""
    for ol in element.find_all('ol'):
        parts = []
        for i, li in enumerate(ol.find_all('li'), 1):
            li_text = li.get_text(' ', strip=True)
            if li_text:
                parts.append(f'{i}. {li_text}')
        ol.replace_with(' '.join(parts))


def cleanup_text(text: str) -> str:
    """Post-process extracted text to fix spacing around operators and punctuation."""
    text = re.sub(r'\(\s+', '(', text)      # (  a  → (a
    text = re.sub(r'\s+\)', ')', text)      # a  )  → a)
    text = re.sub(r'\s+,', ',', text)       # a , b → a, b
    text = re.sub(r'\s+\.', '.', text)      # a . b → a.b
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def clean_text(element) -> str:
    """Extract and clean text from an element, removing extra whitespace.
    Handles <sup>/<sub> tags, fraction tables, and math symbol images."""
    if element is None:
        return ""
    convert_math_images(element)
    convert_math_notation(element)
    convert_fraction_tables(element)
    convert_mathml(element)
    convert_ordered_lists(element)
    text = element.get_text(separator=" ", strip=True)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = cleanup_text(text)
    return text


LETTER_TO_OPTION = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4}


def parse_indiabix_topic_page(url: str, section: str, topic: str = "") -> list[dict]:
    """Parse a single IndiaBix topic page (one page of questions)."""
    questions: list[dict] = []
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return questions

    soup = BeautifulSoup(resp.text, "lxml")

    # Extract shared direction/context (paragraph sentences, passage, instructions)
    shared_context: str = ""
    shared_images: list[str] = []
    direction_div = soup.select_one("div.direction-div div.direction-text")
    if direction_div:
        shared_context = clean_text(direction_div)
        shared_images = extract_images_from_html(direction_div, url)

    containers = soup.select("div.bix-div-container")
    if not containers:
        print(f"  [WARN] No question containers found on {url}")
        return questions

    for container in containers:
        qtxt_div = container.select_one("div.bix-td-qtxt")
        question_text = clean_text(qtxt_div) if qtxt_div else ""

        if not question_text:
            continue

        # Prepend shared context (passage, paragraph, directions) to question
        if shared_context:
            if question_text.strip().lower() == "(solve as per the direction given above)":
                question_text = shared_context
            else:
                question_text = shared_context + "\n" + question_text

        # Extract question-specific images
        q_images: list[str] = []
        if qtxt_div:
            q_images = extract_images_from_html(qtxt_div, url)

        # Parse options
        options: list[str] = []
        option_rows = container.select("div.bix-opt-row")
        for row in option_rows:
            opt_val_div = row.select_one("div.bix-td-option-val div.flex-wrap")
            if opt_val_div:
                opt_text = clean_text(opt_val_div)
                if opt_text:
                    options.append(opt_text)

        if not options:
            continue

        # Get correct answer letter from hidden input
        correct_letter = ""
        hidden_input = container.select_one("input.jq-hdnakq")
        if hidden_input:
            correct_letter = hidden_input.get("value", "").strip().upper()

        # Find correct answer text
        correct_text = ""
        if correct_letter and correct_letter in LETTER_TO_OPTION:
            idx = LETTER_TO_OPTION[correct_letter]
            if idx < len(options):
                correct_text = options[idx]

        if not correct_text:
            continue

        # Combine shared images with question images
        all_images = list(dict.fromkeys(shared_images + q_images))

        q = {
            "id": _next_id(section),
            "topic": topic,
            "question": question_text,
            "options": options,
            "correct": correct_text,
            "section": section,
        }
        if all_images:
            if len(all_images) == 1:
                q["image"] = all_images[0]
            else:
                q["images"] = all_images

        questions.append(q)

    return questions


def get_indiabix_topic_links(category_url: str) -> list[tuple[str, str]]:
    """Get all topic links from an IndiaBix topic listing page.
    Returns list of (topic_name, topic_url)."""
    topics: list[tuple[str, str]] = []
    try:
        resp = SESSION.get(category_url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] Failed to fetch {category_url}: {e}")
        return topics

    soup = BeautifulSoup(resp.text, "lxml")
    topic_list = soup.select("div.topics-wrapper ul li a")
    for a_tag in topic_list:
        href = a_tag.get("href", "")
        name = clean_text(a_tag)
        if href and name and href != category_url:
            full_url = urljoin(category_url, href)
            topics.append((name, full_url))
    return topics


def get_indiabix_pagination_urls(topic_url: str) -> list[str]:
    """Get all pagination page URLs for an IndiaBix topic.
    Handles gaps from '...' in pagination by generating all intermediate page URLs."""
    urls: list[str] = [topic_url]
    try:
        resp = SESSION.get(topic_url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [WARN] Could not fetch pagination for {topic_url}: {e}")
        return urls

    soup = BeautifulSoup(resp.text, "lxml")

    # Find pagination links from ul.pagination
    page_links = soup.select("ul.pagination li.page-item a.page-link")
    found_urls: dict[int, str] = {}
    for link in page_links:
        href = link.get("href", "").strip()
        txt = link.get_text(strip=True)
        if href and href != "#" and txt.isdigit():
            page_num = int(txt)
            full_url = urljoin(topic_url, href)
            if full_url != topic_url:
                found_urls[page_num] = full_url

    if not found_urls:
        return urls

    max_page = max(found_urls.keys())
    if max_page <= 1:
        return urls

    # Generate missing page URLs using the last page URL pattern
    last_url = found_urls[max_page]
    # Pattern: .../{sectionID}{page:03d}
    # Extract the last path segment and find the trailing digits
    last_segment = last_url.rstrip('/').split('/')[-1]
    # Find the section ID prefix (digits before the page number)
    match = re.match(r'^(\d{3})(\d{3})$', last_segment)
    if match:
        section_id = match.group(1)
        # Generate all intermediate page URLs
        for page in range(2, max_page + 1):
            if page not in found_urls:
                seg = f'{section_id}{page:03d}'
                gen_url = last_url.replace(last_segment, seg)
                found_urls[page] = gen_url

    # Add sorted by page number
    for page in sorted(found_urls.keys()):
        if found_urls[page] not in urls:
            urls.append(found_urls[page])

    return urls


def scrape_indiabix() -> dict[str, list[dict]]:
    """Scrape all aptitude questions from IndiaBix."""
    all_questions: dict[str, list[dict]] = {
        "quantitative": [],
        "logical": [],
        "verbal": [],
    }

    sources = {
        "quantitative": "https://www.indiabix.com/aptitude/questions-and-answers/",
        "logical": "https://www.indiabix.com/logical-reasoning/questions-and-answers/",
        "verbal": "https://www.indiabix.com/verbal-ability/questions-and-answers/",
    }

    # Additional sources mapped to sections
    sources_di = {
        "quantitative": "https://www.indiabix.com/data-interpretation/questions-and-answers/",
    }
    sources_nvr = {
        "logical": "https://www.indiabix.com/non-verbal-reasoning/questions-and-answers/",
    }
    sources_vr = {
        "logical": "https://www.indiabix.com/verbal-reasoning/questions-and-answers/",
    }

    for section, cat_url in sources.items():
        print(f"\n{'='*60}")
        print(f"Scraping IndiaBix {section} from {cat_url}")
        print(f"{'='*60}")
        topics = get_indiabix_topic_links(cat_url)
        if not topics:
            print(f"  No topics found. Trying direct page scrape...")
            # Some category pages have questions directly
            qs = parse_indiabix_topic_page(cat_url, section, topic=cat_url)
            all_questions[section].extend(qs)
            print(f"  Got {len(qs)} questions from direct page")
        else:
            print(f"  Found {len(topics)} topics")
            for topic_name, topic_url in topics:
                print(f"  Topic: {topic_name} ({topic_url})")
                page_urls = get_indiabix_pagination_urls(topic_url)
                for page_url in page_urls:
                    qs = parse_indiabix_topic_page(page_url, section, topic=topic_name)
                    all_questions[section].extend(qs)
                    print(f"    Page: {len(qs)} questions (total {len(all_questions[section])})")
                    time.sleep(0.3)  # Be polite

    # Scrape data interpretation as quantitative
    for section, cat_url in sources_di.items():
        print(f"\n{'='*60}")
        print(f"Scraping IndiaBix data-interpretation -> {section}")
        print(f"{'='*60}")
        topics = get_indiabix_topic_links(cat_url)
        if topics:
            print(f"  Found {len(topics)} data-interpretation topics")
            for topic_name, topic_url in topics:
                print(f"  Topic: {topic_name} ({topic_url})")
                page_urls = get_indiabix_pagination_urls(topic_url)
                for page_url in page_urls:
                    qs = parse_indiabix_topic_page(page_url, section, topic=topic_name)
                    all_questions[section].extend(qs)
                    print(f"    Page: {len(qs)} questions (total {len(all_questions[section])})")
                    time.sleep(0.3)

    # Scrape non-verbal reasoning as logical
    for section, cat_url in sources_nvr.items():
        print(f"\n{'='*60}")
        print(f"Scraping IndiaBix non-verbal-reasoning -> {section}")
        print(f"{'='*60}")
        topics = get_indiabix_topic_links(cat_url)
        if topics:
            print(f"  Found {len(topics)} non-verbal reasoning topics")
            for topic_name, topic_url in topics:
                print(f"  Topic: {topic_name} ({topic_url})")
                page_urls = get_indiabix_pagination_urls(topic_url)
                for page_url in page_urls:
                    qs = parse_indiabix_topic_page(page_url, section, topic=topic_name)
                    all_questions[section].extend(qs)
                    print(f"    Page: {len(qs)} questions (total {len(all_questions[section])})")
                    time.sleep(0.3)

    # Scrape verbal reasoning as logical
    for section, cat_url in sources_vr.items():
        print(f"\n{'='*60}")
        print(f"Scraping IndiaBix verbal-reasoning -> {section}")
        print(f"{'='*60}")
        topics = get_indiabix_topic_links(cat_url)
        if topics:
            print(f"  Found {len(topics)} verbal reasoning topics")
            for topic_name, topic_url in topics:
                print(f"  Topic: {topic_name} ({topic_url})")
                page_urls = get_indiabix_pagination_urls(topic_url)
                for page_url in page_urls:
                    qs = parse_indiabix_topic_page(page_url, section, topic=topic_name)
                    all_questions[section].extend(qs)
                    print(f"    Page: {len(qs)} questions (total {len(all_questions[section])})")
                    time.sleep(0.3)

    return all_questions


def scrape_geeksforgeeks() -> dict[str, list[dict]]:
    """Scrape aptitude questions from GeeksforGeeks (basic support)."""
    all_qs: dict[str, list[dict]] = {"quantitative": [], "logical": [], "verbal": []}
    # GeeksforGeeks has a different structure - needs JavaScript rendering often
    # Basic text-based extraction as fallback
    print("\nGeeksforGeeks scraping: site requires JS for full content. Skipping for now.")
    return all_qs


def scrape_careerride() -> dict[str, list[dict]]:
    """Scrape aptitude questions from CareerRide (basic support)."""
    all_qs: dict[str, list[dict]] = {"quantitative": [], "logical": [], "verbal": []}
    print("\nCareerRide scraping: site structure is tutorial-based, not MCQ-friendly. Skipping for now.")
    return all_qs


def merge_with_existing(new_questions: list[dict]) -> list[dict]:
    """Fresh scrape — return new questions only (no merge with old data)."""
    print(f"\nTotal scraped: {len(new_questions)}")
    return new_questions


def flatten_and_save(all_questions: dict, label: str = "intermediate") -> int:
    """Flatten questions from all sections, merge with existing, and save."""
    new_qs = []
    for section in ["quantitative", "logical", "verbal"]:
        new_qs.extend(all_questions.get(section, []))
    merged = merge_with_existing(new_qs)
    output = {"questions": merged}
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  [{label}] Saved {len(merged)} questions to {OUTPUT_JSON}")
    return len(merged)


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("APTITUDE QUESTION BANK SCRAPER WITH IMAGE SUPPORT")
    print("=" * 60)

    all_questions: dict[str, list[dict]] = {
        "quantitative": [],
        "logical": [],
        "verbal": [],
    }

    # IndiaBix is the primary source
    ib_results = scrape_indiabix()
    for section in all_questions:
        all_questions[section].extend(ib_results.get(section, []))

    # GeeksforGeeks and CareerRide as secondary/fallback
    gf_results = scrape_geeksforgeeks()
    for section in all_questions:
        all_questions[section].extend(gf_results.get(section, []))

    cr_results = scrape_careerride()
    for section in all_questions:
        all_questions[section].extend(cr_results.get(section, []))

    # Flatten all questions and save
    new_questions: list[dict] = []
    for section in ["quantitative", "logical", "verbal"]:
        new_questions.extend(all_questions.get(section, []))

    total = flatten_and_save(all_questions, "final")

    # Stats
    with_image = [q for q in json.loads(OUTPUT_JSON.read_text(encoding='utf-8')).get('questions', []) if "image" in q or "images" in q]
    print(f"\nQuestions with images: {len(with_image)}")
    for section in ["quantitative", "logical", "verbal"]:
        count = len([q for q in json.loads(OUTPUT_JSON.read_text(encoding='utf-8')).get('questions', []) if q.get("section") == section])
        img_count = len([q for q in with_image if q.get("section") == section])
        print(f"  {section}: {count} total, {img_count} with images")


if __name__ == "__main__":
    main()
