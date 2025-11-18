#!/usr/bin/env python
"""
Daily pipeline that retrieves recent arXiv submissions in large-model categories,
tries to extract public contact emails for authors, and stores them in a CSV.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import logging
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import tz

ARXIV_API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "ResearchIntelBot/0.1 (+https://github.com/bytedance/author_parser)"
EMAIL_REGEX = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

DEFAULT_CATEGORIES = [
    "cs.CL",
    "cs.LG",
    "cs.AI",
    "stat.ML",
]

DEFAULT_TARGET_KEYWORDS = [
    "deepseek",
    "anthropic",
    "google brain",
    "deepmind",
    "tsinghua",
    "pku",
    "mit",
    "stanford",
]


@dataclass
class AuthorContact:
    name: str
    affiliation: str | None
    email: str | None
    source: str
    source_url: str
    last_seen: dt.datetime
    paper_title: str | None = None
    paper_id: str | None = None
    notes: str | None = None

    def key(self) -> str:
        identifier = self.email or f"{self.name.lower()}|{self.affiliation or ''}"
        return identifier.strip()


@dataclass
class ContactStore:
    csv_path: str
    _records: Dict[str, AuthorContact] = field(default_factory=dict)

    def load(self) -> None:
        if not os.path.exists(self.csv_path):
            return

        with open(self.csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    record = AuthorContact(
                        name=row["name"],
                        affiliation=row.get("affiliation") or None,
                        email=row.get("email") or None,
                        source=row.get("source") or "arxiv",
                        source_url=row.get("source_url") or "",
                        last_seen=dt.datetime.fromisoformat(row["last_seen"]),
                        paper_title=row.get("paper_title") or None,
                        paper_id=row.get("paper_id") or None,
                        notes=row.get("notes") or None,
                    )
                    self._records[record.key()] = record
                except Exception as exc:  # pragma: no cover - defensive
                    logging.warning("Skipping malformed row %s (%s)", row, exc)

    def upsert(self, contact: AuthorContact) -> None:
        key = contact.key()
        existing = self._records.get(key)
        if existing:
            # Refresh last seen and enrich missing fields.
            existing.last_seen = max(existing.last_seen, contact.last_seen)
            for field_name in ("email", "affiliation", "paper_title", "paper_id", "notes"):
                if not getattr(existing, field_name) and getattr(contact, field_name):
                    setattr(existing, field_name, getattr(contact, field_name))
            if contact.source_url:
                existing.source_url = contact.source_url
            return

        self._records[key] = contact

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
        fieldnames = [
            "name",
            "affiliation",
            "email",
            "source",
            "source_url",
            "last_seen",
            "paper_title",
            "paper_id",
            "notes",
        ]
        with open(self.csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in sorted(self._records.values(), key=lambda r: (r.name.lower(), r.last_seen), reverse=False):
                writer.writerow(
                    {
                        "name": record.name,
                        "affiliation": record.affiliation or "",
                        "email": record.email or "",
                        "source": record.source,
                        "source_url": record.source_url,
                        "last_seen": record.last_seen.isoformat(),
                        "paper_title": record.paper_title or "",
                        "paper_id": record.paper_id or "",
                        "notes": record.notes or "",
                    }
                )


def fetch_arxiv_entries(categories: Sequence[str], max_results: int) -> List[feedparser.FeedParserDict]:
    query = " OR ".join(f"cat:{cat}" for cat in categories)
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    logging.info("Querying arXiv: %s", params)
    resp = requests.get(ARXIV_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    return feed.entries


def filtered_entries(entries: Iterable[feedparser.FeedParserDict], past_days: int) -> List[feedparser.FeedParserDict]:
    cutoff = dt.datetime.now(tz.UTC) - dt.timedelta(days=past_days)
    filtered = []
    for entry in entries:
        updated = None
        if "updated_parsed" in entry and entry.updated_parsed:
            updated = dt.datetime(*entry.updated_parsed[:6], tzinfo=tz.UTC)
        elif "published_parsed" in entry and entry.published_parsed:
            updated = dt.datetime(*entry.published_parsed[:6], tzinfo=tz.UTC)

        if updated and updated >= cutoff:
            filtered.append(entry)
    logging.info("Filtered to %d entries newer than %s", len(filtered), cutoff.isoformat())
    return filtered


def build_author_search_url(name: str) -> str:
    return f"https://arxiv.org/search/?searchtype=author&query={requests.utils.quote(name)}"


def extract_emails_from_html(html: str) -> List[str]:
    emails = EMAIL_REGEX.findall(html or "")
    return list(dict.fromkeys(email.lower() for email in emails))


def scrape_author_page(name: str, session: requests.Session) -> tuple[list[str], str]:
    url = build_author_search_url(name)
    logging.debug("Fetching author page %s", url)
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    result = soup.find("ol", {"class": "breathe-horizontal"})
    notes = ""
    html_chunks = []
    if result:
        first_li = result.find("li")
        if first_li:
            html_chunks.append(str(first_li))
            link = first_li.find("a")
            if link and link.get("href"):
                notes = f"Matched {link.get_text(strip=True)}"
    emails = extract_emails_from_html(" ".join(html_chunks) if html_chunks else resp.text)
    return emails, notes


def author_affiliation(author_dict: Dict[str, Any]) -> Optional[str]:
    raw = author_dict.get("affiliation")
    if isinstance(raw, list):
        return raw[0].get("name") if raw else None
    if isinstance(raw, dict):
        return raw.get("name")
    return raw


def should_prioritize(name: str, affiliation: Optional[str], keywords: Sequence[str]) -> bool:
    haystack = " ".join(filter(None, [name, affiliation or ""])).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def contacts_from_entry(
    entry: feedparser.FeedParserDict,
    keywords: Sequence[str],
    session: requests.Session,
    request_interval: float,
    full_scan: bool,
) -> List[AuthorContact]:
    contacts: List[AuthorContact] = []
    paper_id = entry.get("id", "")
    paper_title = entry.get("title", "").replace("\n", " ").strip()
    updated = None
    if "updated_parsed" in entry and entry.updated_parsed:
        updated = dt.datetime(*entry.updated_parsed[:6], tzinfo=tz.UTC)
    else:
        updated = dt.datetime.now(tz.UTC)

    authors = entry.get("authors", [])
    for author in authors:
        name = author.get("name", "").strip()
        affiliation = author_affiliation(author)
        contact = AuthorContact(
            name=name,
            affiliation=affiliation,
            email=None,
            source="arxiv",
            source_url=paper_id,
            last_seen=updated,
            paper_title=paper_title,
            paper_id=paper_id,
        )
        if full_scan or should_prioritize(name, affiliation, keywords):
            try:
                emails, notes = scrape_author_page(name, session)
                if emails:
                    contact.email = emails[0]
                    contact.notes = notes or "Email found on arXiv author search page"
                else:
                    contact.notes = "No email found on author page"
                time.sleep(request_interval)
            except requests.HTTPError as exc:
                contact.notes = f"HTTP error fetching author page: {exc.response.status_code}"
            except Exception as exc:  # pragma: no cover - defensive
                contact.notes = f"Error scraping author page: {exc}"
        else:
            contact.notes = "Skipped detailed scrape (keyword mismatch)"

        contacts.append(contact)
    return contacts


def serialize_entry(entry: feedparser.FeedParserDict) -> Dict[str, Any]:
    authors = entry.get("authors", [])
    serialized_authors = []
    for author in authors:
        serialized_authors.append(
            {
                "name": author.get("name"),
                "affiliation": author_affiliation(author),
            }
        )
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "summary": entry.get("summary"),
        "updated": entry.get("updated"),
        "published": entry.get("published"),
        "categories": entry.get("tags"),
        "authors": serialized_authors,
        "links": entry.get("links"),
    }


def run_pipeline(
    csv_path: str,
    categories: Sequence[str],
    past_days: int,
    keywords: Sequence[str],
    max_results: int,
    request_interval: float,
    dry_run: bool,
    dump_feed_path: Optional[str],
    full_scan: bool,
) -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    entries = fetch_arxiv_entries(categories, max_results)
    if dump_feed_path:
        os.makedirs(os.path.dirname(dump_feed_path) or ".", exist_ok=True)
        with open(dump_feed_path, "w", encoding="utf-8") as handle:
            json.dump([serialize_entry(entry) for entry in entries], handle, ensure_ascii=False, indent=2)
        logging.info("Dumped %d raw entries to %s", len(entries), dump_feed_path)
    recent_entries = filtered_entries(entries, past_days)

    store = ContactStore(csv_path)
    store.load()

    new_contacts = 0
    for entry in recent_entries:
        contacts = contacts_from_entry(entry, keywords, session, request_interval, full_scan)
        for contact in contacts:
            if not contact.email:
                continue
            existing_before = len(store._records)
            store.upsert(contact)
            if len(store._records) > existing_before:
                new_contacts += 1

    if dry_run:
        logging.info("Dry-run enabled: skipping CSV write. %d potential new contacts.", new_contacts)
    else:
        store.save()
        logging.info("Persisted CSV to %s with %d total contacts", csv_path, len(store._records))

    return new_contacts


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily research intelligence pipeline for arXiv.")
    parser.add_argument(
        "--csv-path",
        default="research_contacts.csv",
        help="Path to the CSV file where contacts are stored.",
    )
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="Comma-separated arXiv categories to query (default targets LLM work).",
    )
    parser.add_argument(
        "--past-days",
        type=int,
        default=1,
        help="Only include papers updated within the past N days.",
    )
    parser.add_argument(
        "--target-keywords",
        default=",".join(DEFAULT_TARGET_KEYWORDS),
        help="Comma-separated keywords to prioritize (names, orgs, affiliations).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=200,
        help="Max arXiv results to fetch per run.",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=1.5,
        help="Seconds to wait between supplemental page fetches.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline without writing to the CSV.",
    )
    parser.add_argument(
        "--dump-feed",
        default=None,
        help="Optional path to store the raw arXiv API response (JSON) for debugging.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="Attempt to scrape every author regardless of keyword match (more requests).",
    )
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    configure_logging(args.log_level)
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    keywords = [k.strip() for k in args.target_keywords.split(",") if k.strip()]
    new_contacts = run_pipeline(
        csv_path=args.csv_path,
        categories=categories,
        past_days=args.past_days,
        keywords=keywords,
        max_results=args.max_results,
        request_interval=args.request_interval,
        dry_run=args.dry_run,
        dump_feed_path=args.dump_feed,
        full_scan=args.full_scan,
    )
    logging.info("Run complete. %d new contacts detected.", new_contacts)


if __name__ == "__main__":
    main()

