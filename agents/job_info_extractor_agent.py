from model.models import AgentState
from util import is_job_detail_url, with_retry_and_rate_limit, parse_date_string
import logging
logger = logging.getLogger(__name__)
async def job_info_extractor_agent(state: AgentState) -> AgentState:
    """
    Extract job information from specific job posting URL using structured output
    """
    if not state.links_to_visit:
        return state

    # Look for job-specific URLs in the queue
    job_url = None
    temp_links = []

    while state.links_to_visit:
        url = state.links_to_visit.popleft()
        if is_job_detail_url(url):
            job_url = url
            # Put remaining links back
            for remaining in temp_links:
                state.links_to_visit.appendleft(remaining)
            break
        else:
            temp_links.append(url)

    if not job_url:
        # Put all links back and return
        for link in temp_links:
            state.links_to_visit.appendleft(link)
        return state

    state.current_page_url = job_url
    print(f"📄 Extracting job info from: {job_url}")

    # Extract job information with retry logic
    job_info = await with_retry_and_rate_limit(
        state,
        extract_job_details_modern,
        job_url,
        state.user_job_preference
    )

    if job_info:
        state.add_job(job_info)
        print(f"✅ Added job: {job_info.title} at {job_info.company}")
    else:
        print(f"❌ Failed to extract job info from {job_url}")

    state.mark_visited(job_url)
    return state
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
import asyncio
import re


from model.models import JobInfo, JobExtraction
from typing import  Optional
from langchain_community.document_transformers import Html2TextTransformer

async def extract_job_details_modern(url: str, user_preference: str) -> Optional[JobInfo]:
    """
    Extract job details using modern LangChain with_structured_output method
    """
    try:
        # Step 1: Load page content
        logger.debug("📥 Loading page content...")
        loader = AsyncChromiumLoader([url])
        docs = await asyncio.to_thread(loader.load)
        html2text = Html2TextTransformer(ignore_links=False)
        docs_transformed = html2text.transform_documents(docs)
        page_content = docs_transformed[0].page_content

        # Step 4: Initialize LLM with structured output
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(JobExtraction)

        # Step 5: Create extraction prompt
        extraction_prompt = f"""
        Extract job information from the following webpage content.

        User is looking for: {user_preference}

        Webpage Content:
        {page_content}

        Please extract all available job information. If information is not available, use appropriate defaults.
        Focus on accuracy and only extract information that is clearly present in the content.
        """

        # Step 6: Extract structured data
        result = structured_llm.invoke(extraction_prompt)

        # Step 7: Convert to JobInfo object
        job_info = JobInfo(
            title=result.job_title,
            company=result.company_name,
            description=result.job_description,
            application_info=result.application_method or url,
            posted_date=parse_date_string(result.posted_date),
            source_url=url
        )
        logger.info(f"✅ Successfully extracted job: {job_info.title} at {job_info.company}")

        return job_info

    except Exception as e:
        logger.error(f"❌ Failed to extract job details from {url}: {str(e)}")
        raise Exception(f"Failed to extract job details from {url}: {str(e)}")

