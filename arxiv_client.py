import requests
import feedparser
import time
import os
import sys

# Base URL for the arXiv API query interface
ARXIV_API_BASE_URL = 'http://export.arxiv.org/api/query?'

def handle_api_error(error_entry):
    """Prints details from an arXiv API error entry."""
    summary = error_entry.get('summary', 'Unknown error detail')
    error_id = error_entry.get('id', '#')
    error_link = error_entry.get('link', '#')
    print(f"[!] arXiv API Error: {summary}")
    if error_link != '#':
        print(f"    More info link: {error_link}")
    elif error_id != '#':
         print(f"    Error ID: {error_id}")

def search_arxiv(query, start=0, max_results=10, sort_by="submittedDate", sort_order="descending"):
    """
    Searches the arXiv API and returns parsed results.

    Args:
        query (str): The search query string (e.g., 'ti:"quantum computing" AND au:smith').
        start (int): The starting index for the results (for paging).
        max_results (int): Maximum number of results to retrieve per page.
        sort_by (str): Field to sort results by ('relevance', 'lastUpdatedDate', 'submittedDate').
        sort_order (str): Order of sorting ('ascending', 'descending').

    Returns:
        feedparser.FeedParserDict: Parsed feed data, or None if an error occurs.
    """
    params = {
        'search_query': query,
        'start': start,
        'max_results': max_results,
        'sortBy': sort_by,
        'sortOrder': sort_order
    }

    print(f"[*] Querying arXiv: '{query}' (start={start}, max={max_results}, sort={sort_by}/{sort_order})")

    try:
        # Make the API request
        response = requests.get(ARXIV_API_BASE_URL, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # Introduce a delay as recommended by arXiv API terms (especially for repeated calls like paging)
        time.sleep(1.5) # Slightly increased delay

        # Parse the Atom XML feed
        feed = feedparser.parse(response.content)

        # --- Enhanced Error Checking ---
        if feed.bozo:
            # Bozo means the feed is somehow malformed
            exc = feed.bozo_exception
            if isinstance(exc, feedparser.NonXMLContentType):
                print(f"[!] Error: Received non-XML content type: {response.headers.get('content-type', 'Unknown')}")
                print("    Response text:", response.text[:500]) # Show beginning of response
            elif isinstance(exc, requests.exceptions.HTTPError):
                 print(f"[!] Error: HTTP Error during parsing: {exc}")
            else:
                print(f"[!] Warning: Malformed feed received. Error: {exc}")
            # Attempt to check for embedded API errors even if malformed
            if feed.entries and 'Error' in feed.entries[0].get('title', ''):
                 handle_api_error(feed.entries[0])
            return None # Indicate significant parsing issue

        # Check for API errors embedded in the feed (as per docs 3.4)
        if feed.entries and 'Error' in feed.entries[0].get('title', ''):
            handle_api_error(feed.entries[0])
            return None # API returned an error entry

        if not feed.entries and int(feed.feed.get('opensearch_totalresults', 0)) > 0:
             print(f"[!] Warning: Feed indicates total results > 0 but no entries received for start index {start}.")
             print(f"    Check if the start index exceeds the total results.")

        return feed

    except requests.exceptions.Timeout:
        print("[!] Error: Request timed out. arXiv API might be slow or unreachable.")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"[!] Error: Network connection error: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[!] Error: HTTP error occurred: {e} - {e.response.status_code}")
        # Try to parse the response anyway for potential error messages from arXiv
        try:
            error_feed = feedparser.parse(e.response.content)
            if error_feed.entries and 'Error' in error_feed.entries[0].get('title', ''):
                handle_api_error(error_feed.entries[0])
            else:
                print("    Response content:", e.response.text[:500]) # Show snippet if not standard error
        except Exception:
            print("    Could not parse error response content.") # Error parsing the error
        return None
    except requests.exceptions.RequestException as e:
        print(f"[!] Error: A requests error occurred: {e}")
        return None
    except Exception as e:
        # Catch other potential errors during processing/parsing
        print(f"[!] Error: An unexpected error occurred during arXiv search/parsing: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
        return None


def download_pdf(entry, directory="."):
    """
    Downloads the PDF for a given entry.

    Args:
        entry (feedparser.FeedParserDict.entry): The parsed entry data.
        directory (str): The directory to save the PDF in.

    Returns:
        str: The full path to the downloaded PDF file, or None if download fails.
    """
    pdf_link = None
    arxiv_id_full = entry.get('id', '').split('/abs/')[-1] # e.g., 1707.08567v1
    arxiv_id_base = arxiv_id_full.split('v')[0] # e.g., 1707.08567

    if not arxiv_id_base:
        print("[!] Error: Could not extract arXiv ID from entry.")
        return None

    for link in entry.get('links', []):
        if link.get('title') == 'pdf':
            pdf_link = link.get('href')
            break
        elif link.get('type') == 'application/pdf':
             pdf_link = link.get('href') # Fallback

    if not pdf_link:
        print(f"[!] Error: No PDF link found for entry {arxiv_id_full}.")
        return None

    # Ensure link uses http or https explicitly
    if pdf_link.startswith("//"):
        pdf_link = "https:" + pdf_link # Default to https
    elif not pdf_link.startswith(("http://", "https://")):
         print(f"[!] Warning: Unusual PDF link format: {pdf_link}. Attempting download anyway.")
         # Might need more robust URL handling here depending on variations

    # Sanitize ID for filename and create filename
    safe_id = "".join(c if c.isalnum() or c in ['.', '-'] else '_' for c in arxiv_id_full)
    filename = f"{safe_id}.pdf"
    filepath = os.path.join(directory, filename)

    # Create directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)

    # Check if file already exists
    if os.path.exists(filepath):
        print(f"[*] PDF already exists at: {filepath}")
        return filepath

    print(f"[*] Attempting to download PDF from: {pdf_link}")
    print(f"    Saving to: {filepath}")

    try:
        response = requests.get(pdf_link, stream=True, timeout=60) # Increase timeout for potentially large files
        response.raise_for_status() # Check for download errors (404, etc.)

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        block_size = 8192 # 8KB chunks

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=block_size):
                f.write(chunk)
                downloaded_size += len(chunk)
                # Simple progress indicator
                if total_size > 0:
                    done = int(50 * downloaded_size / total_size)
                    sys.stdout.write(f"\r    Progress: [{'=' * done}{' ' * (50 - done)}] {downloaded_size / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB")
                    sys.stdout.flush()
                else:
                     sys.stdout.write(f"\r    Downloaded: {downloaded_size / (1024*1024):.2f} MB (Total size unknown)")
                     sys.stdout.flush()
        sys.stdout.write('\n') # Move to next line after progress bar
        print(f"[+] Successfully downloaded {filename}")
        return filepath

    except requests.exceptions.Timeout:
         print(f"\n[!] Error: Download timed out for {filename}.")
         if os.path.exists(filepath): os.remove(filepath) # Clean up partial download
         return None
    except requests.exceptions.RequestException as e:
        print(f"\n[!] Error: Failed to download PDF: {e}")
        if os.path.exists(filepath): os.remove(filepath) # Clean up partial download
        return None
    except IOError as e:
        print(f"\n[!] Error: Could not write file to disk: {e}")
        if os.path.exists(filepath): os.remove(filepath) # Clean up partial download
        return None
    except Exception as e:
         print(f"\n[!] Error: An unexpected error occurred during download: {e}")
         if os.path.exists(filepath): os.remove(filepath) # Clean up partial download
         return None