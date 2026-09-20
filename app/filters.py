"""Deterministic pre-filters for Ayush's Europe-focused early-career search.

The cheap rules here intentionally only reject clear mismatches. Ambiguous
cases are preserved for the OpenAI evaluation stage, where the full candidate
profile and complete JD can be considered together.
"""
import re
from datetime import datetime, timezone, timedelta
import yaml

FILTERS_CONFIG_PATH = "filters.yaml"


def _load_config(path: str = FILTERS_CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_config = _load_config()

PRIORITY_TITLE_KEYWORDS = _config["priority_title_keywords"]
TITLE_ALLOW_KEYWORDS = _config["title_allow_keywords"]
EXCLUSION_KEYWORDS = _config["exclusion_keywords"]
SENIORITY_EXCLUSION_KEYWORDS = _config.get("seniority_exclusion_keywords", [])
SENIORITY_PREFERRED_KEYWORDS = _config.get("seniority_preferred_keywords", [])
MAX_REQUIRED_YEARS = int(_config.get("max_required_years", 3))
MAX_POST_AGE_DAYS = int(_config.get("max_post_age_days", 14))
LOCATION_ALLOW_PATTERNS = _config["location_allow_patterns"]
STACK_DEALBREAKERS = _config["stack_dealbreakers"]
STACK_CORE = _config["stack_core"]
TRUNCATED_DESCRIPTION_MIN_CHARS = _config["truncated_description_min_chars"]


def _compile_keyword_alternation(keywords: list[str], config_key: str) -> re.Pattern:
    if not keywords:
        raise ValueError(
            f"filters.yaml's '{config_key}' is empty — add at least one keyword."
        )
    return re.compile("(" + "|".join(re.escape(k) for k in keywords) + ")", re.IGNORECASE)


_priority_re = _compile_keyword_alternation(PRIORITY_TITLE_KEYWORDS, "priority_title_keywords")
_title_allow_re = _compile_keyword_alternation(TITLE_ALLOW_KEYWORDS, "title_allow_keywords")
_exclusion_re = _compile_keyword_alternation(EXCLUSION_KEYWORDS, "exclusion_keywords")
_seniority_exclusion_re = (
    _compile_keyword_alternation(SENIORITY_EXCLUSION_KEYWORDS, "seniority_exclusion_keywords")
    if SENIORITY_EXCLUSION_KEYWORDS
    else None
)
_seniority_preferred_re = (
    _compile_keyword_alternation(SENIORITY_PREFERRED_KEYWORDS, "seniority_preferred_keywords")
    if SENIORITY_PREFERRED_KEYWORDS
    else None
)
_location_res = [re.compile(p, re.IGNORECASE) for p in LOCATION_ALLOW_PATTERNS]
_dealbreaker_res = [re.compile(p, re.IGNORECASE) for p in STACK_DEALBREAKERS]
_core_res = [re.compile(p, re.IGNORECASE) for p in STACK_CORE]

_html_tag_re = re.compile(r"<[^>]+>")
_space_re = re.compile(r"\s+")

# Deliberately anchored to phrases that normally describe candidate experience
# instead of blindly matching every number followed by "years".
_YEARS_PATTERNS = [
    re.compile(r"\b(\d{1,2})\+\s*(?:years?|yrs?)\b", re.IGNORECASE),
    re.compile(r"\bat\s+least\s+(\d{1,2})\s*(?:years?|yrs?)\b", re.IGNORECASE),
    re.compile(r"\bminimum(?:\s+of)?\s+(\d{1,2})\s*(?:years?|yrs?)\b", re.IGNORECASE),
    re.compile(
        r"\b(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional|commercial|industry|software|development|engineering)\s+experience\b",
        re.IGNORECASE,
    ),
]


def strip_html(html_or_text: str) -> str:
    if not html_or_text:
        return ""
    return _space_re.sub(" ", _html_tag_re.sub(" ", html_or_text)).strip()


def looks_truncated(description: str) -> bool:
    text = strip_html(description or "")
    if not text:
        return True
    if text.endswith("…") or text.endswith("...") or text.rstrip().endswith(".."):
        return True
    return len(text) < TRUNCATED_DESCRIPTION_MIN_CHARS


def seniority_title_is_allowed(title: str) -> bool:
    title = title or ""
    return not (_seniority_exclusion_re and _seniority_exclusion_re.search(title))


def has_preferred_seniority_signal(title: str) -> bool:
    return bool(_seniority_preferred_re and _seniority_preferred_re.search(title or ""))


def title_is_relevant(title: str) -> bool:
    title = title or ""
    if not seniority_title_is_allowed(title):
        return False
    if _priority_re.search(title):
        return True
    if not _title_allow_re.search(title):
        return False
    if _exclusion_re.search(title):
        return False
    return True


def location_is_allowed(location: str) -> bool:
    loc = location or ""
    return any(p.search(loc) for p in _location_res)


def extract_explicit_required_years(description: str) -> int | None:
    """Return the highest clearly stated minimum-years requirement we find.

    We avoid generic "X years" matches because JDs often mention product age,
    education duration, benefits, or company history. Only requirement-shaped
    phrases are considered.
    """
    text = strip_html(description)
    years: list[int] = []
    for pattern in _YEARS_PATTERNS:
        years.extend(int(m.group(1)) for m in pattern.finditer(text))
    return max(years) if years else None


def experience_requirement_is_allowed(description: str) -> bool:
    years = extract_explicit_required_years(description)
    return years is None or years <= MAX_REQUIRED_YEARS


def _parse_posted_at(value) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            # Lever uses epoch milliseconds.
            seconds = float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        text = str(value).strip()
        if text.isdigit():
            number = int(text)
            seconds = number / 1000.0 if number > 10_000_000_000 else number
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def posted_at_is_fresh(posted_at, now: datetime | None = None) -> bool:
    """Reject only when the source gave us a parseable date that is too old."""
    dt = _parse_posted_at(posted_at)
    if dt is None:
        return True
    now = now or datetime.now(timezone.utc)
    return dt >= now - timedelta(days=MAX_POST_AGE_DAYS)


def jd_stack_mismatch(description: str) -> bool:
    text = strip_html(description)
    if not text:
        return False
    has_dealbreaker = any(p.search(text) for p in _dealbreaker_res)
    has_core = any(p.search(text) for p in _core_res)
    return has_dealbreaker and not has_core


def passes_filters(job: dict) -> bool:
    if not title_is_relevant(job.get("title", "")):
        return False
    if not location_is_allowed(job.get("location", "")):
        return False
    if not posted_at_is_fresh(job.get("posted_at")):
        return False
    description = job.get("description", "")
    if not experience_requirement_is_allowed(description):
        return False
    if jd_stack_mismatch(description):
        return False
    return True
