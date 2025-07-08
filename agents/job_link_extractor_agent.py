from typing import Optional, Dict, List


from model.models import AgentState, LinkCategorization
from util import with_retry_and_rate_limit
from langchain_openai import ChatOpenAI
from urllib.parse import urlparse
import logging
logger = logging.getLogger(__name__)
from playwright.async_api import async_playwright

async def job_link_extractor_agent(state: AgentState) -> AgentState:
    """
    Extract job listing links from current page with modern structured output
    """
    if not state.links_to_visit:
        return state

    current_url = state.links_to_visit.popleft()
    state.current_page_url = current_url

    print(f"🔍 Extracting links from: {current_url}")

    # Extract page links with retry logic
    page_data = await with_retry_and_rate_limit(
        state,
        extract_page_links_modern,  # extract_page_links_modern,
        current_url,
        state.user_job_preference
    )

    if page_data:
        # Add discovered links to visit queue
        new_links = page_data.get('job_detail_links', [])
        listing_links = page_data.get('job_listing_pages', [])
        nav_links = page_data.get('navigation_links', [])

        # Prioritize job detail links, then listings, then navigation
        all_new_links = new_links + listing_links + nav_links[:3]  # Limit nav links
        state.add_links_to_visit(all_new_links)

        print(f"✅ Found {len(new_links)} job links, {len(listing_links)} listing pages, {len(nav_links)} nav links")
    else:
        print(f"❌ Failed to extract links from {current_url}")

    state.mark_visited(current_url)
    return state

async def extract_page_links_modern(url: str, user_preference: str) -> Optional[Dict[str, List[str]]]:
    """
    Extract and categorize links using modern structured output
    """
    try:
        # Load page and extract links with context
        logger.debug("🌐 Loading page with Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # ⭐ NEW: Wait for dynamic content and scroll to trigger lazy loading
            await page.wait_for_timeout(3000)  # Wait for JS to load

            # Scroll to bottom to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            # Extract links with context
            logger.debug("🔗 Extracting links from page...")

            links_data = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links.map(link => ({
                        href: link.href,
                        text: link.textContent.trim(),
                        context: link.closest('div,section,article')?.textContent.slice(0, 200) || ''
                    })).filter(link => link.href && link.text && link.href.startsWith('http'));
                }
            """)
            await browser.close()
        logger.debug(f"RAW LINKS: {links_data}")
        logger.info(f"📊 Found {len(links_data)} total links on page")

        base_domain = urlparse(url).netloc
        # Group links by URL to remove duplicates but keep best metadata
        unique_links = {}
        for link in links_data:
            href = link['href']
            if href not in unique_links:
                unique_links[href] = link
            else:
                # Keep the link with more text/context
                existing = unique_links[href]
                if len(link['text']) > len(existing['text']) or len(link['context']) > len(existing['context']):
                    unique_links[href] = link

        # Filter same-domain links

        filtered_links = []
        for link in unique_links.values():
            link_domain = urlparse(link['href']).netloc

            # Only keep same-domain links
            if link_domain == base_domain:
                filtered_links.append(link)
            else:
                logger.debug(f"🚫 Skipping external link: {link['href']} (domain: {link_domain})")

        logger.info(f"🏠 Filtered to {len(filtered_links)} same-domain links (removed external links)")
        # Use modern structured output for link categorization
        logger.debug("🤖 Initializing LLM for advanced link categorization...")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(LinkCategorization)

        # ⭐ NEW: Create enhanced links text for analysis with more metadata
        links_text = "\n".join([
            f"URL: {link['href']}\n"
            f"Text: {link['text']}\n"
            f"Context: {link['context'][:100]}\n"
            f"---"
            for link in filtered_links  # Analyze top 30 links
        ])

        categorization_prompt = f"""
               User is looking for jobs related to: {user_preference}

               Available links from comprehensive extraction:
               {links_text}

               Categorize these links into:
               1. job_detail_links: Direct links to individual job postings (look for job IDs, specific positions)
               2. job_listing_pages: Links to pages with multiple job listings (search results, category pages)
               3. navigation_links: Pagination, search, filter, or navigation links that might lead to more jobs

               Consider:
               - URLs with job IDs or position identifiers
               - Links with job-related keywords in URL path
               - Context suggesting individual vs. multiple listings
               - Form actions for job searches
               - Navigation elements for pagination

               Focus on links most relevant to the user's job preferences.
               Return empty lists if no relevant links are found.
               """

        logger.debug("🧠 Running enhanced LLM categorization...")
        categorized = structured_llm.invoke(categorization_prompt)

        result = {
            "job_detail_links": categorized.job_detail_links,
            "job_listing_pages": categorized.job_listing_pages,
            "navigation_links": categorized.navigation_links
        }

        total_categorized = sum(len(links) for links in result.values())
        logger.info(f"✅ Categorized {total_categorized} relevant links: "
                    f"{len(result['job_detail_links'])} job details, "
                    f"{len(result['job_listing_pages'])} listings, "
                    f"{len(result['navigation_links'])} navigation")

        return result

    except Exception as e:
        logger.error(f"❌ Failed to extract links from {url}: {str(e)}")
        raise Exception(f"Failed to extract links from {url}: {str(e)}")







