import asyncio
import re


from model.models import AgentState
from datetime import datetime, timedelta
from typing import List, Optional



import logging
logger = logging.getLogger(__name__)
from urllib.parse import urlparse, urlunparse


def parse_date_string(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime object"""
    if not date_str:
        return None

    try:
        # Handle relative dates
        if 'ago' in date_str.lower():
            if 'day' in date_str:
                days_ago = int(re.search(r'(\d+)', date_str).group(1))
                return datetime.now() - timedelta(days=days_ago)
            elif 'hour' in date_str:
                hours_ago = int(re.search(r'(\d+)', date_str).group(1))
                return datetime.now() - timedelta(hours=hours_ago)

        # Handle standard date formats
        return   parse_date_string(date_str)

    except Exception:
        return None


def is_job_detail_url(url: str) -> bool:
    """Heuristic to identify job detail URLs"""
    job_indicators = ['/job/', '/jobs/', '/career/', '/careers/', '/position/', '/opening/' , "/listings/"]
    return any(indicator in url.lower() for indicator in job_indicators)


async def with_retry_and_rate_limit(state: AgentState, operation, *args, **kwargs):
    """Execute operation with retry logic and rate limiting"""
    for attempt in range(state.max_retries):
        try:
            await state.rate_limit_delay()
            result = await operation(*args, **kwargs)
            state.reset_retry_count()
            return result

        except Exception as e:
            state.retry_count = attempt + 1
            error_msg = f"Attempt {attempt + 1}/{state.max_retries} failed: {str(e)}"

            if attempt == state.max_retries - 1:
                state.record_error(f"Operation failed after {state.max_retries} attempts: {str(e)}")
                return None
            else:
                wait_time = state.delay_between_requests * (2 ** attempt)
                print(f"{error_msg}. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)

    return None


def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('job_scraper.log'),
            logging.StreamHandler()
        ]
    )


def validate_environment():
    """Validate required environment variables"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found in environment variables. Please add it to your .env file.")

    logger = logging.getLogger(__name__)
    logger.info("🔑 Environment variables loaded successfully")
    logger.info(f"🤖 OpenAI API Key: {'*' * 10 + OPENAI_API_KEY[-4:] if OPENAI_API_KEY else 'NOT SET'}")

    return OPENAI_API_KEY


def normalize_url(url: str) -> str:
    """
    Normalize URL using furl library for robust handling
    """
    try:
        from furl import furl

        # Parse URL with furl
        f = furl(url, fragment=None)

        # Remove fragment
        # f.fragment = None

        # Normalize host (lowercase)
        if f.host:
            f.host = f.host.lower()

        # Remove trailing slash from path (unless root)
        if f.path.segments and f.path.segments[-1] == '':
            f.path.segments.pop()

        # Remove common tracking parameters
        tracking_params = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'campaign',
            'sessionid', 'jsessionid', 'phpsessid', '_ga', '_gid'
        ]

        for param in tracking_params:
            if param in f.args:
                del f.args[param]

        return f.url

    except ImportError:
        logger.warning("furl library not available, falling back to basic normalization")
        # Fallback to basic urllib normalization
        try:
            parsed = urlparse(url)

            # Basic normalization
            parsed = parsed._replace(fragment='')
            path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path

            return urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                path,
                parsed.params,
                parsed.query,
                ''
            ))
        except Exception as e:
            logger.warning(f"Failed to normalize URL {url}: {e}")
            return url

    except Exception as e:
        logger.warning(f"Failed to normalize URL {url} with furl: {e}")
        # Fallback to original URL
        return url


def validate_and_filter_links(
        links: List[str],
        current_url: str,
        links_visited: set,
        links_to_visit: list,
        base_domain: Optional[str] = None
) -> List[str]:
    """
    Validate and filter links before adding to queue

    Args:
        links: List of URLs to validate
        current_url: Current page URL
        links_visited: Set of already visited URLs
        links_to_visit: Current queue of links to visit
        base_domain: Optional base domain to restrict to

    Returns:
        List of validated, unique links
    """
    if not links:
        return []

    logger.debug(f"🔍 Validating {len(links)} links...")

    # Normalize current URL for comparison
    normalized_current = normalize_url(current_url)

    # Convert existing collections to normalized sets for fast lookup
    normalized_visited = {normalize_url(url) for url in links_visited}
    normalized_queue = {normalize_url(url) for url in links_to_visit}

    # Get base domain if not provided
    if not base_domain:
        try:
            base_domain = urlparse(current_url).netloc.lower()
        except:
            base_domain = None

    valid_links = []
    seen_normalized = set()

    for link in links:
        try:
            # Basic URL validation
            if not link or not isinstance(link, str):
                continue

            # Must be HTTP/HTTPS
            if not link.startswith(('http://', 'https://')):
                logger.debug(f"⚠️ Skipping non-HTTP link: {link}")
                continue

            # Parse URL to validate structure
            parsed = urlparse(link)
            if not parsed.netloc:
                logger.debug(f"⚠️ Skipping invalid URL: {link}")
                continue

            # Normalize for comparison
            normalized_link = normalize_url(link)

            # Skip if already processed (visited, queued, or seen in this batch)
            if normalized_link in normalized_visited:
                logger.debug(f"⚠️ Already visited: {link}")
                continue

            if normalized_link in normalized_queue:
                logger.debug(f"⚠️ Already in queue: {link}")
                continue

            if normalized_link in seen_normalized:
                logger.debug(f"⚠️ Duplicate in current batch: {link}")
                continue

            # Skip if it's the same as current page
            if normalized_link == normalized_current:
                logger.debug(f"⚠️ Same as current page: {link}")
                continue

            # ⭐ UPDATED: Strict domain validation (no external links allowed)
            if base_domain:
                link_domain = parsed.netloc.lower()
                if link_domain != base_domain:
                    logger.debug(f"⚠️ External link blocked: {link} (domain: {link_domain})")
                    continue

            # Additional quality checks
            if len(link) > 500:  # Extremely long URLs are suspicious
                logger.debug(f"⚠️ URL too long: {link}")
                continue

            # Skip common non-content URLs
            skip_patterns = [
                r'\.pdf$', r'\.doc$', r'\.zip$', r'\.exe$',  # File downloads
                r'/api/', r'/ajax/', r'/wp-admin/', r'/admin/',  # API/admin endpoints
                r'javascript:', r'mailto:', r'tel:', r'ftp:',  # Non-HTTP protocols
                r'#$', r'\?print=', r'/print/',  # Print versions
            ]

            if any(re.search(pattern, link, re.IGNORECASE) for pattern in skip_patterns):
                logger.debug(f"⚠️ Skipping pattern match: {link}")
                continue

            # Add to valid links
            valid_links.append(link)  # Keep original URL, not normalized
            seen_normalized.add(normalized_link)

        except Exception as e:
            logger.warning(f"⚠️ Error validating link {link}: {e}")
            continue

    logger.info(f"✅ Validated {len(valid_links)} unique links from {len(links)} candidates")

    # Log some examples for debugging
    if valid_links:
        logger.debug(f"📋 Sample valid links: {valid_links[:3]}")

    return valid_links