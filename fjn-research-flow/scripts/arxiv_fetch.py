#!/usr/bin/env python3
"""arXiv fetch helper with local cache, cross-process throttling, and retries."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback.
    fcntl = None  # type: ignore[assignment]


API_URL = "http://export.arxiv.org/api/query"
OPENALEX_URL = "https://api.openalex.org/works"
NS = "http://www.w3.org/2005/Atom"
ID_RE = re.compile(r"^(?:arXiv:)?(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.I)
ARXIV_ID_RE = re.compile(r"(?:arxiv(?:\.org/(?:abs|pdf)/|[:./])|10\.48550/arxiv\.)(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", re.I)
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_CACHE_TTL_HOURS = 24.0
DEFAULT_MIN_INTERVAL_SECONDS = 3.2
DEFAULT_RETRIES = 5
DEFAULT_TIMEOUT_SECONDS = 45
SKILL_ROOT = Path(__file__).resolve().parents[1]


def stderr(message: str) -> None:
    print(message, file=sys.stderr)


def default_cache_dir() -> Path:
    env_path = os.environ.get("FJN_ARXIV_CACHE_DIR")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".cache" / "fjn-research-flow" / "arxiv"


def read_contact_file(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        return ""
    return ""


def default_contact_file_candidates() -> list[Path]:
    cwd = Path.cwd().resolve()
    candidates: list[Path] = []
    for base in [cwd, *cwd.parents]:
        candidates.extend([base / ".research_flow" / "arxiv_contact.txt", base / ".arxiv_contact"])
        if base == SKILL_ROOT:
            break
    candidates.extend([SKILL_ROOT / ".local" / "arxiv_contact.txt", SKILL_ROOT / ".arxiv_contact"])
    return candidates


def resolve_contact(contact_file: Path | None = None) -> str:
    if contact_file is not None:
        contact = read_contact_file(contact_file.expanduser())
        if contact:
            return contact
    for path in default_contact_file_candidates():
        contact = read_contact_file(path)
        if contact:
            return contact
    return os.environ.get("FJN_ARXIV_CONTACT") or os.environ.get("ARXIV_CONTACT") or ""


def user_agent(contact_file: Path | None = None) -> str:
    contact = resolve_contact(contact_file)
    suffix = f" ({contact})" if contact else ""
    return f"fjn-research-flow-arxiv-fetch/1.0{suffix}"


def normalize_arxiv_id(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^arXiv:", "", value, flags=re.I)
    return value


def looks_like_arxiv_id(value: str) -> bool:
    return bool(ID_RE.match(value.strip()))


def cache_key(parts: list[str]) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


def cache_path(cache_dir: Path, kind: str, key: str) -> Path:
    return cache_dir / kind / f"{key}.json"


def load_cache(path: Path, ttl_hours: float | None, allow_stale: bool) -> tuple[Any | None, bool]:
    if not path.exists():
        return None, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, False
    age_seconds = time.time() - float(payload.get("fetched_at", 0))
    is_fresh = ttl_hours is None or age_seconds <= ttl_hours * 3600
    if is_fresh or allow_stale:
        return payload.get("data"), is_fresh
    return None, False


def write_cache(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": time.time(), "data": data}
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


@contextmanager
def throttled(cache_dir: Path, min_interval_seconds: float):
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / ".arxiv_request.lock"
    stamp_path = cache_dir / ".last_request"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            last_request = 0.0
            if stamp_path.exists():
                try:
                    last_request = float(stamp_path.read_text(encoding="utf-8").strip() or "0")
                except (OSError, ValueError):
                    last_request = 0.0
            wait_seconds = min_interval_seconds - (time.time() - last_request)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            yield
            stamp_path.write_text(str(time.time()), encoding="utf-8")
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def request_bytes(url: str, args: argparse.Namespace) -> bytes:
    headers = {"User-Agent": user_agent(args.contact_file), "Accept": "application/atom+xml,application/pdf,*/*"}
    last_error: Exception | None = None
    for attempt in range(args.retries + 1):
        try:
            with throttled(args.cache_dir, args.min_interval):
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=args.timeout) as response:
                    return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRY_STATUS_CODES or attempt >= args.retries:
                break
            wait_seconds = retry_after_seconds(exc)
            if wait_seconds is None:
                wait_seconds = min(90.0, 2.0 ** attempt * args.min_interval + random.uniform(0, 1.0))
            stderr(f"WARN: arXiv HTTP {exc.code}; retry {attempt + 1}/{args.retries} after {wait_seconds:.1f}s")
            time.sleep(wait_seconds)
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt >= args.retries:
                break
            wait_seconds = min(90.0, 2.0 ** attempt * args.min_interval + random.uniform(0, 1.0))
            stderr(f"WARN: arXiv request failed ({exc}); retry {attempt + 1}/{args.retries} after {wait_seconds:.1f}s")
            time.sleep(wait_seconds)
    raise RuntimeError(f"arXiv request failed after retries: {last_error}")


def parse_feed(body: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    papers: list[dict[str, Any]] = []
    for entry in root.findall(f"{{{NS}}}entry"):
        raw_id = entry.findtext(f"{{{NS}}}id", "")
        arxiv_id = raw_id.split("/abs/")[-1].split("v")[0]
        title = " ".join((entry.findtext(f"{{{NS}}}title", "") or "").split())
        abstract = " ".join((entry.findtext(f"{{{NS}}}summary", "") or "").split())
        authors = [
            " ".join((author.findtext(f"{{{NS}}}name", "") or "").split())
            for author in entry.findall(f"{{{NS}}}author")
        ]
        categories = [category.get("term", "") for category in entry.findall(f"{{{NS}}}category")]
        published = entry.findtext(f"{{{NS}}}published", "")
        updated = entry.findtext(f"{{{NS}}}updated", "")
        papers.append(
            {
                "id": arxiv_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published": published[:10],
                "updated": updated[:10],
                "categories": categories,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            }
        )
    return papers


def meta_values(text: str, name: str) -> list[str]:
    pattern = re.compile(
        r"<meta\s+name=[\"']" + re.escape(name) + r"[\"']\s+content=([\"'])(.*?)\1\s*/?>",
        flags=re.I | re.S,
    )
    return [html.unescape(" ".join(value.split())) for _, value in pattern.findall(text)]


def parse_abs_html(body: bytes, arxiv_id: str) -> dict[str, Any]:
    text = body.decode("utf-8", errors="ignore")
    title = meta_values(text, "citation_title")
    authors = meta_values(text, "citation_author")
    date = meta_values(text, "citation_date")
    abstract = meta_values(text, "citation_abstract")
    pdf_url = meta_values(text, "citation_pdf_url")
    paper_id = meta_values(text, "citation_arxiv_id") or [arxiv_id]
    published = date[0].replace("/", "-") if date else ""
    return {
        "id": normalize_arxiv_id(paper_id[0]),
        "title": title[0] if title else "",
        "authors": authors,
        "abstract": abstract[0] if abstract else "",
        "published": published,
        "updated": "",
        "categories": [],
        "pdf_url": pdf_url[0] if pdf_url else f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
        "metadata_source": "arxiv_abs_html_fallback",
    }


def fetch_abs_html_fallback(arxiv_id: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    url = f"https://arxiv.org/abs/{urllib.parse.quote(arxiv_id)}"
    body = request_bytes(url, args)
    return [parse_abs_html(body, arxiv_id)]


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    size = max(position for positions in index.values() for position in positions) + 1
    words = [""] * size
    for word, positions in index.items():
        for position in positions:
            words[position] = word
    return " ".join(words)


def extract_arxiv_id(work: dict[str, Any]) -> str:
    candidates: list[str] = []
    ids = work.get("ids") or {}
    candidates.extend(str(value) for value in ids.values() if value)
    primary_location = work.get("primary_location") or {}
    candidates.extend(str(primary_location.get(key)) for key in ("landing_page_url", "pdf_url") if primary_location.get(key))
    for location in work.get("locations") or []:
        candidates.extend(str(location.get(key)) for key in ("landing_page_url", "pdf_url") if location.get(key))
    for candidate in candidates:
        match = ARXIV_ID_RE.search(candidate)
        if match:
            return normalize_arxiv_id(match.group(1))
    return ""


def openalex_fallback(args: argparse.Namespace) -> list[dict[str, Any]]:
    params = {"search": args.query, "per-page": str(min(max(args.max, 1), 200))}
    contact = resolve_contact(args.contact_file)
    if contact and "@" in contact:
        params["mailto"] = contact
    url = f"{OPENALEX_URL}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": user_agent(args.contact_file), "Accept": "application/json"}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        payload = json.load(response)

    papers: list[dict[str, Any]] = []
    for work in payload.get("results", []):
        arxiv_id = extract_arxiv_id(work)
        primary_location = work.get("primary_location") or {}
        pdf_url = primary_location.get("pdf_url") or ""
        abs_url = primary_location.get("landing_page_url") or ""
        if arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        papers.append(
            {
                "id": arxiv_id or (work.get("ids") or {}).get("openalex", ""),
                "title": work.get("display_name") or "",
                "authors": [
                    ((authorship.get("author") or {}).get("display_name") or "")
                    for authorship in work.get("authorships", [])
                ],
                "abstract": abstract_from_inverted_index(work.get("abstract_inverted_index")),
                "published": work.get("publication_date") or "",
                "updated": "",
                "categories": [concept.get("display_name", "") for concept in (work.get("concepts") or [])[:5]],
                "pdf_url": pdf_url,
                "abs_url": abs_url or (work.get("ids") or {}).get("openalex", ""),
                "metadata_source": "openalex_fallback",
                "openalex_id": (work.get("ids") or {}).get("openalex", ""),
                "doi": (work.get("ids") or {}).get("doi", ""),
            }
        )
    return papers


def query_url(query: str, max_results: int, sort_by: str, sort_order: str) -> str:
    query = query.strip()
    if query.startswith("id:"):
        arxiv_id = normalize_arxiv_id(query.split(":", 1)[1])
        params = {"id_list": arxiv_id}
    elif looks_like_arxiv_id(query):
        params = {"id_list": normalize_arxiv_id(query)}
    else:
        params = {
            "search_query": query,
            "start": "0",
            "max_results": str(max_results),
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def query_arxiv_id(query: str) -> str:
    query = query.strip()
    if query.startswith("id:"):
        return normalize_arxiv_id(query.split(":", 1)[1])
    if looks_like_arxiv_id(query):
        return normalize_arxiv_id(query)
    return ""


def search(args: argparse.Namespace) -> int:
    url = query_url(args.query, args.max, args.sort_by, args.sort_order)
    key = cache_key(["search", url])
    path = cache_path(args.cache_dir, "search", key)
    ttl_hours = None if args.cache_ttl_hours < 0 else args.cache_ttl_hours
    if not args.fresh:
        cached, is_fresh = load_cache(path, ttl_hours, allow_stale=False)
        if cached is not None and is_fresh:
            print(json.dumps(cached, ensure_ascii=False, indent=2))
            return 0
    try:
        body = request_bytes(url, args)
        papers = parse_feed(body)
        write_cache(path, papers)
        print(json.dumps(papers, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report and use stale cache when possible.
        fallback_error: Exception | None = None
        try:
            arxiv_id = query_arxiv_id(args.query)
            if arxiv_id:
                papers = fetch_abs_html_fallback(arxiv_id, args)
            elif not args.no_openalex_fallback:
                papers = openalex_fallback(args)
            else:
                papers = []
            if papers:
                stderr(f"WARN: arXiv export API failed; returned fallback metadata after: {exc}")
                write_cache(path, papers)
                print(json.dumps(papers, ensure_ascii=False, indent=2))
                return 0
        except Exception as inner_exc:  # noqa: BLE001 - preserve original failure and fallback failure.
            fallback_error = inner_exc
        cached, _ = load_cache(path, ttl_hours, allow_stale=True)
        if cached is not None:
            stderr(f"WARN: using stale arXiv cache after live request failed: {exc}")
            print(json.dumps(cached, ensure_ascii=False, indent=2))
            return 0
        stderr(f"ERROR: {exc}")
        if fallback_error is not None:
            stderr(f"ERROR: fallback metadata request also failed: {fallback_error}")
        stderr("FALLBACK: use OpenAlex/Semantic Scholar/venue pages/repository README, and record arXiv access failure in the stage manifest.")
        return 2


def download(args: argparse.Namespace) -> int:
    arxiv_id = normalize_arxiv_id(args.arxiv_id)
    args.dir.mkdir(parents=True, exist_ok=True)
    output_path = args.dir / f"{arxiv_id.replace('/', '_')}.pdf"
    if output_path.exists() and output_path.stat().st_size > 10 * 1024 and not args.fresh:
        print(f"Already exists: {output_path} ({output_path.stat().st_size // 1024} KB)")
        return 0
    url = f"https://arxiv.org/pdf/{urllib.parse.quote(arxiv_id)}.pdf"
    try:
        body = request_bytes(url, args)
    except Exception as exc:  # noqa: BLE001 - CLI report.
        stderr(f"ERROR: {exc}")
        return 2
    output_path.write_bytes(body)
    size = output_path.stat().st_size
    if size <= 10 * 1024:
        output_path.unlink(missing_ok=True)
        stderr("ERROR: downloaded PDF is too small; likely an error page")
        return 2
    print(f"Downloaded: {output_path} ({size // 1024} KB)")
    return 0


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    parser.add_argument("--contact-file", type=Path, default=None, help="Read contact email/URL from a local text file.")
    parser.add_argument("--cache-ttl-hours", type=float, default=DEFAULT_CACHE_TTL_HOURS)
    parser.add_argument("--fresh", action="store_true", help="Ignore fresh cache and force a live arXiv request.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--min-interval", type=float, default=DEFAULT_MIN_INTERVAL_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search arXiv or fetch a specific arXiv ID.")
    search_parser.add_argument("query")
    search_parser.add_argument("--max", type=int, default=10)
    search_parser.add_argument("--sort-by", default="relevance", choices=["relevance", "lastUpdatedDate", "submittedDate"])
    search_parser.add_argument("--sort-order", default="descending", choices=["ascending", "descending"])
    search_parser.add_argument("--no-openalex-fallback", action="store_true")
    add_common_args(search_parser)
    search_parser.set_defaults(func=search)

    download_parser = subparsers.add_parser("download", help="Download a PDF by arXiv ID.")
    download_parser.add_argument("arxiv_id")
    download_parser.add_argument("--dir", type=Path, default=Path("papers"))
    add_common_args(download_parser)
    download_parser.set_defaults(func=download)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.cache_dir = args.cache_dir.expanduser()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())