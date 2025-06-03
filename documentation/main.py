import re
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import json
import httpx
import os
import asyncio
import sys
import io
import logging
from typing import Dict, List, Union, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Force UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.platform == "win32":
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except:
        locale.setlocale(locale.LC_ALL, '')
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'

# Initialize MCP
load_dotenv()
mcp = FastMCP("docs")

# Constants
USER_AGENT = "docs-app/1.0"
SERPER_URL = "https://google.serper.dev/search"
MAX_TEXT_LENGTH = 15000

DOCS_URLS = {
    # "langchain": "python.langchain.com/docs",
    # "llama-index": "docs.llamaindex.ai/en/stable",
    # "openai": "platform.openai.com/docs",
    "flutter":"docs.flutter.dev",
    "stackoverflow": "stackoverflow.com",
}

def format_rpc_response(result: Optional[Union[Dict, List]] = None, 
                       error: Optional[Dict] = None) -> Dict:
    """Format response according to JSON-RPC 2.0 specification"""
    return {
        "jsonrpc": "2.0",
        "result": result,
        "error": error,
        "id": None  # Will be set by MCP
    }

async def search_web(query: str, num_results: int = 5) -> Dict:
    """Search the web using Serper API"""
    payload = json.dumps({"q": query, "num": num_results})
    headers = {
        "X-API-KEY": os.getenv("SERPER_API_KEY"),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(SERPER_URL, headers=headers, data=payload)
            response.raise_for_status()
            data = response.json()
            #print the json with only orgainc data where i can see this print tatement
            #print(data)
            print( "STEP 1 ORGANINC ORGAINSE ======================",data.get("organic", []))  # Debugging line to see the organic results
            return format_rpc_response(result=data.get("organic", []))
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return format_rpc_response(error={
            "code": -32000,
            "message": f"Search failed: {str(e)}"
        })

async def fetch_url(url: str) -> Dict:
    """Fetch and clean content from a URL"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            
            if not response.encoding:
                response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "nav", "footer"]):
                element.decompose()
            
            text = soup.get_text()
            text = ' '.join(text.split())
            return format_rpc_response(result=text[:MAX_TEXT_LENGTH])
            
    except Exception as e:
        logger.error(f"Error fetching {url}: {str(e)}")
        return format_rpc_response(error={
            "code": -32001,
            "message": f"Failed to fetch URL: {str(e)}"
        })

@mcp.tool()
async def get_doc(query: str, library: str) -> Dict:
    """
    Searched the documentation  or webpage of stackoverflow or flutter
    for a given query to find the solution

    Args: 
        query (str): The search query to find relevant documentation.
        library (str): The library or documentation site to search in.
    Returns:
        Dict: A dictionary containing the search results or an error message.
    1. Search the web using the Serper API with the provided query.
    2. Fetch the top results and extract their content.
    3. Return the combined content of the top results.
    Raises:
        Exception: If an error occurs during the search or content fetching.
    """
    try:
        if library not in DOCS_URLS:
            return format_rpc_response(error={
                "code": -32602,
                "message": f"Unsupported library. Choose from: {list(DOCS_URLS.keys())}"
            })
        
        site_query = f"site:{DOCS_URLS[library]} {query}"
        search_result = await search_web(site_query)
        
        if search_result.get("error"):
            return search_result
        
        results = search_result.get("result", [])
        if not results:
            return format_rpc_response(error={
                "code": -32004,
                "message": "No results found"
            })
        
        combined_content = []
        for result in results:  # Limit to top 3 results
            print("getting the line from the result", result.get("link", ""))
            content = await fetch_url(result.get("link", ""))
            if content and content.get("result"):
                combined_content.append(content["result"])
        
        if not combined_content:
            return format_rpc_response(error={
                "code": -32005,
                "message": "Could not fetch any content"
            })
        
        full_content = ' '.join(combined_content)
        return format_rpc_response(result=full_content[:10000])
        
    except Exception as e:
        logger.error(f"Error in get_doc: {str(e)}")
        return format_rpc_response(error={
            "code": -32603,
            "message": f"Internal error: {str(e)}"
        })

if __name__ == "__main__":
    mcp.run(transport="stdio")