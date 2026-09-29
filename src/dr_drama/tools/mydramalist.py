"""Temporary unofficial MDL provider; replace when official access is available."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
import re
import ssl
import time
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv


class MetadataError(Exception):
    """A configuration, provider, or response validation failure."""


def text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.lower() not in {"n/a", "unknown", "not yet rated", "?"} else None


def integer(value: Any) -> int | None:
    value = str(value).strip().replace(",", "").lstrip("#")
    return int(value) if re.fullmatch(r"[0-9]+", value) else None


def string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = list(dict.fromkeys(item for entry in value if (item := text(entry))))
    # Empty scraper output cannot distinguish missing markup from an empty list.
    return cleaned or None


def codes(value: Any, mapping: dict[str, str]) -> list[str] | None:
    values = value if isinstance(value, list) else [value]
    result = []
    for entry in values:
        label = text(entry)
        if label:
            code = mapping.get(label.casefold())
            if code:
                result.append(code)
    return list(dict.fromkeys(result)) or None


def normalize_metadata(details: dict, cast: dict, slug: str) -> dict[str, Any]:
    """Map provider values to CSV metadata fields; unknown values remain None.

    Cast is restricted to up to five Main Role entries in provider order.
    Public popularity is a rank, not the rating rank or watcher count.
    """
    identifier = re.match(r"^(\d+)(?:-|$)", slug)
    title = text(details.get("title"))
    if not identifier or not title:
        raise MetadataError("Details are missing a usable title or record ID.")
    returned_slug = text(details.get("slug"))
    if returned_slug and returned_slug.split("-", 1)[0] != identifier.group(1):
        raise MetadataError("The returned record ID does not match the selected result.")
    aired = text(details.get("aired"))
    first_date = re.split(r"\s+-\s+", aired)[0] if aired else ""
    year_match = re.search(r"\b(?:19|20)\d{2}\b", first_date)
    year = int(year_match.group()) if year_match else integer(details.get("year"))
    if year is not None and not 1900 <= year <= 2100:
        year = None
    suffix = re.search(r" \((\d{4})\)$", title)
    if suffix and (year is None or int(suffix.group(1)) == year):
        title = title[:suffix.start()]
    try:
        rating = float(details.get("rating"))
        if not 0 < rating <= 10:
            rating = None
    except (ValueError, TypeError):
        rating = None
    votes_match = re.search(r"scored by\s+([\d,]+)\s+users?", str(details.get("score_details", "")), re.I)
    votes = integer(votes_match.group(1)) if votes_match else None
    if votes == 0:
        rating = None
    popularity = integer(details.get("popularity"))
    if popularity == 0:
        popularity = None
    episodes = integer(details.get("episodes"))
    if episodes == 0:
        episodes = None
    grouped_cast = cast.get("cast", {})
    main = grouped_cast.get("Main Role", []) if isinstance(grouped_cast, dict) else []
    actors = string_list([entry.get("name") for entry in main if isinstance(entry, dict)]) if isinstance(main, list) else None
    return {
        "canonical_title": title,
        "original_title": text(details.get("native_title")),
        "release_year": year,
        "country": codes(details.get("country"), {"south korea": "KR", "kr": "KR", "japan": "JP", "jp": "JP", "china": "CN", "cn": "CN", "taiwan": "TW", "tw": "TW", "thailand": "TH", "th": "TH", "hong kong": "HK", "hk": "HK"}),
        "original_language": codes(details.get("original_language") or details.get("language"), {"korean": "ko", "ko": "ko", "japanese": "ja", "ja": "ja", "chinese": "zh", "mandarin": "zh", "zh": "zh", "thai": "th", "th": "th", "english": "en", "en": "en"}),
        "genres": string_list(details.get("genres")),
        "main_cast": actors[:5] if actors else None,
        "number_of_episodes": episodes,
        "public_rating": rating,
        "public_vote_count": votes,
        "popularity": popularity,
        "popularity_metric": "rank" if popularity is not None else None,
        "synopsis": text(details.get("synopsis")),
        "keywords": string_list(details.get("tags")),
        "external_api_id": identifier.group(1),
        "metadata_source": "mydramalist",
        "source_url": f"https://mydramalist.com/{quote(slug, safe='-')}",
        "metadata_retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


class MyDramaListClient:
    """Search and fetch metadata with timeouts, pacing, and bounded retries."""

    def __init__(self, base_url: str, api_key: str = "", key_header: str = "", *, transport=None, sleep=time.sleep):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise MetadataError("MDL_API_BASE_URL must be an HTTPS URL without credentials, query, or fragment.")
        if api_key and (not re.fullmatch(r"[A-Za-z0-9-]+", key_header) or key_header.lower() in {"host", "content-length"}):
            raise MetadataError("Set MDL_API_KEY_HEADER to the authentication header documented by your deployment.")
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self._last_request = None
        self.client = httpx.Client(
            headers={key_header: api_key} if api_key else {},
            timeout=30, follow_redirects=False,
            verify=ssl.create_default_context(), transport=transport,
        )

    @classmethod
    def from_env(cls, env_path=None):
        """Load local settings without overriding existing environment variables."""
        load_dotenv(env_path, override=False)
        base = os.getenv("MDL_API_BASE_URL", "").strip()
        if not base:
            raise MetadataError("Set MDL_API_BASE_URL in .env before searching.")
        return cls(base, os.getenv("MDL_API_KEY", ""), os.getenv("MDL_API_KEY_HEADER", ""))

    def close(self):
        self.client.close()

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else 2 ** attempt
        except ValueError:
            try:
                delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError):
                delay = 2 ** attempt
        if delay > 30:
            raise MetadataError("Provider requested a longer retry delay. Try again later.")
        return max(1, delay)

    def _get(self, path: str) -> dict:
        for attempt in range(3):
            if self._last_request is not None:
                self.sleep(max(0, 1 - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            try:
                response = self.client.get(self.base_url + path)
            except httpx.TransportError:
                if attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise MetadataError("Cannot reach metadata provider after three attempts.") from None
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                self.sleep(self._retry_delay(response, attempt))
                continue
            if not response.is_success:
                raise MetadataError(f"Metadata provider returned HTTP {response.status_code}. Try again later or check configuration.")
            try:
                data = response.json()
            except ValueError:
                raise MetadataError("Metadata provider returned invalid JSON.") from None
            if not isinstance(data, dict) or data.get("error"):
                raise MetadataError("Metadata provider returned an error or unexpected response.")
            return data
        raise MetadataError("Metadata request failed.")

    def search(self, title: str) -> list[dict]:
        """Return candidates for explicit user selection, never an automatic match."""
        if not title.strip():
            raise MetadataError("Enter a nonempty title.")
        payload = self._get("/api/search/q/" + quote(title.strip(), safe=""))
        results = payload.get("results")
        if not isinstance(results, list):
            raise MetadataError("Search response is missing its results list.")
        candidates = []
        for entry in results:
            if not isinstance(entry, dict):
                raise MetadataError("Search contains an invalid candidate.")
            slug = text(entry.get("slug"))
            if not slug or not re.fullmatch(r"\d+(?:-[\w.-]+)?", slug) or not text(entry.get("title")):
                raise MetadataError("Search candidate is missing a valid title or ID.")
            candidates.append({"title": entry['title'], "slug": slug, "year": entry.get("year"), "url": f"https://mydramalist.com/{slug}"})
        return candidates

    def fetch(self, slug: str) -> tuple[dict, dict, list[str]]:
        """Return normalized metadata, original response payloads, and warnings."""
        if not re.fullmatch(r"\d+(?:-[\w.-]+)?", slug):
            raise MetadataError("Invalid selected record identifier.")
        details = self._get("/api/id/" + quote(slug, safe="-"))
        warnings = []
        try:
            cast = self._get("/api/id/" + quote(slug, safe="-") + "/cast")
        except MetadataError as error:
            cast = {}
            warnings.append(f"Cast unavailable: {error}")
        metadata = normalize_metadata(details, cast, slug)
        missing = [key for key, value in metadata.items() if value is None]
        if missing:
            warnings.append("Unavailable or unrecognized fields: " + ", ".join(missing))
        warnings.append("Confirm this is the intended Korean TV series; the scraper may omit media type and return movies or specials.")
        return metadata, {"details": details, "cast": cast}, warnings
