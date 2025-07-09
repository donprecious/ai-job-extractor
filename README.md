# ai-job-extractor

`ai-job-extractor` is a powerful job scraper that leverages LangChain and LangGraph to automate the job search process. This tool extracts job links from websites and parses key details such as job title, company, location, and description, streamlining your job hunting workflow.

## Blog Post

This repository contains the source code for the project featured in the blog post: **[Getting Started with Agentic AI: Build Your First AI-Powered Web Scraper Using LangGraph & LangChain](https://medium.com/@donprecious/getting-started-with-agentic-ai-build-your-first-ai-powered-web-scraper-using-langgraph-23a652a8e912?source=friends_link&sk=5976d3b377fcbd01d0d77ffd954139be)**.

## Getting Started

Follow these instructions to set up and run the project on your local machine.

### Prerequisites

*   Python 3.8+

### Installation & Setup

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/donprecious/ai-job-extractor.git
    cd ai-job-extractor
    ```

2.  **Create and activate a virtual environment:**
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the required dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

4.  **Set up your environment variables:**
    *   Create a `.env` file by copying the example file:
        ```sh
        cp .env.example .env
        ```
    *   Open the `.env` file and add your API keys (e.g., for OpenAI or other services).

### Running the Project

To start the job scraper, run the main script:
```sh
python main.py
```

The script will then begin the process of finding and extracting job information.