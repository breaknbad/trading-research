"""
resilience_layer.py — Retry wrapper, circuit breaker, and system health for all external calls.
"""
import sys, os, time, logging, functools, requests
from datetime import datetime, timezone
from collections import defaultdict
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, FINNHUB_KEY

# --- Local file logging (survives Supabase outage) ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "resilience.log")

logger = logging.getLogger("resilience")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

# --- Circuit breaker state ---
FAILURE_THRESHOLD = 5
_failure_counts: dict = defaultdict(int)   # endpoint_host -> consecutive failures
_failed_endpoints: set = set()
_system_mode = "NORMAL"  # NORMAL | DEGRADED | SAFE


def _get_host(url: str) -> str:
    return urlparse(url).netloc or url


def _update_mode():
    global _system_mode
    if _failed_endpoints:
        _system_mode = "SAFE" if len(_failed_endpoints) >= 2 else "DEGRADED"
    else:
        _system_mode = "NORMAL"


def _record_success(host: str):
    global _system_mode
    _failure_counts[host] = 0
    _failed_endpoints.discard(host)
    _update_mode()


def _record_failure(host: str):
    _failure_counts[host] += 1
    if _failure_counts[host] >= FAILURE_THRESHOLD:
        _failed_endpoints.add(host)
        logger.critical(f"Circuit OPEN for {host} after {FAILURE_THRESHOLD} consecutive failures — entering SAFE_MODE")
    _update_mode()


def get_system_status() -> dict:
    """Return current system health status."""
    return {
        "mode": _system_mode,
        "failed_endpoints": list(_failed_endpoints),
        "failure_counts": dict(_failure_counts),
    }


def is_entry_allowed() -> bool:
    """In SAFE_MODE, block new entries. Exits always allowed."""
    return _system_mode != "SAFE"


# --- @resilient decorator ---
def resilient(retries=3, backoffs=(1, 2, 4)):
    """Decorator: retries a function with exponential backoff, logs failures."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(retries + 1):
                try:
                    result = fn(*args, **kwargs)
                    return result
                except Exception as e:
                    last_exc = e
                    if attempt < retries:
                        wait = backoffs[min(attempt, len(backoffs) - 1)]
                        logger.warning(f"{fn.__name__} attempt {attempt+1} failed: {e} — retrying in {wait}s")
                        time.sleep(wait)
                    else:
                        logger.error(f"{fn.__name__} failed after {retries+1} attempts: {e}")
            raise last_exc
        return wrapper
    return decorator


# --- resilient_request ---
def resilient_request(method: str, url: str, retries=3, backoffs=(1, 2, 4), **kwargs) -> requests.Response:
    """Wrapper around requests with retry + circuit breaker."""
    host = _get_host(url)
    kwargs.setdefault("timeout", 10)
    last_exc = None

    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            _record_success(host)
            return resp
        except Exception as e:
            last_exc = e
            _record_failure(host)
            if attempt < retries:
                wait = backoffs[min(attempt, len(backoffs) - 1)]
                logger.warning(f"Request {method} {url} attempt {attempt+1} failed: {e} — retry in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"Request {method} {url} exhausted {retries+1} attempts: {e}")

    raise last_exc


if __name__ == "__main__":
    print("System status:", get_system_status())
    print("Entry allowed:", is_entry_allowed())
