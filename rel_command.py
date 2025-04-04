"""
Module for handling the 'rel' command in the arXiv Gemini App.
This command finds related work for a paper using the Serper API.
"""

import json
import requests
import textwrap
import time
import gemini_client

def search_scholar_serper(query, serper_api_key, num_results=10):
    """
    Searches Google Scholar using the Serper API.

    Args:
        query (str): The search query (e.g., paper title).
        serper_api_key (str): Your Serper API key.
        num_results (int): Number of results to request.

    Returns:
        list: A list of dictionaries, each representing a search result,
              or None if an error occurs. Returns empty list if no results found.
    """
    # First try the Scholar endpoint
    search_url = "https://google.serper.dev/scholar"

    # If Scholar endpoint fails, fall back to regular search with site:scholar.google.com
    fallback_search_url = "https://google.serper.dev/search"

    headers = {
        'X-API-KEY': serper_api_key,
        'Content-Type': 'application/json'
    }

    # For Scholar API
    payload = json.dumps({
        "q": query,
        "num": num_results
    })

    # For regular search API (fallback)
    fallback_payload = json.dumps({
        "q": f"{query} site:scholar.google.com",
        "num": num_results
    })

    print(f"[*] Querying Serper Google Scholar: '{query[:60]}...' (Requesting {num_results} results)")

    try:
        # Try Scholar API first
        # Send request to Serper API
        response = requests.post(search_url, headers=headers, data=payload, timeout=20)


        response.raise_for_status()
        search_results = response.json()

        # Extract the relevant 'organic' results list
        organic_results = search_results.get('organic', [])

        # If no results from Scholar API, try fallback
        if not organic_results:
            print("[*] No results from Scholar API, trying regular search...")
            # Send fallback request
            response = requests.post(fallback_search_url, headers=headers, data=fallback_payload, timeout=20)

            response.raise_for_status()
            search_results = response.json()

            organic_results = search_results.get('organic', [])


        print(f"[+] Serper responded with {len(organic_results)} results.")
        return organic_results # Return the list of result dictionaries

    except requests.exceptions.Timeout:
        print("[!] Error: Serper API request timed out.")
        return None
    except requests.exceptions.HTTPError as http_err:
        print(f"[!] Error: Serper API HTTP error occurred: {http_err}")
        try: # Try to print response body for more details
            print(f"    Response Status: {http_err.response.status_code}")
            print(f"    Response Body: {http_err.response.text}")
        except Exception:
             pass
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"[!] Error: Serper API request error occurred: {req_err}")
        return None
    except json.JSONDecodeError:
        print("[!] Error: Could not decode JSON response from Serper API.")
        print(f"    Raw Response: {response.text[:500]}...") # Show beginning of raw response
        return None
    except Exception as e:
        print(f"[!] Error during Serper Scholar search: {e}")
        import traceback
        traceback.print_exc()
        return None

async def handle_rel_command(args_str, state, serper_api_key):
    """
    Handle the 'rel' command to find related work for a paper.

    Args:
        args_str (str): The arguments string (paper number)
        state: The application state
        serper_api_key (str): The Serper API key

    Returns:
        bool: True if successful, False otherwise
    """
    # Check if Serper is enabled
    if not serper_api_key:
        print("[!] Serper API not configured. Cannot use 'rel' command.")
        print("[!] To enable this feature, please set the SERPER_API_KEY environment variable.")
        print("[!] You can get a free API key from https://serper.dev/")
        return False

    # Check if we have results to work with
    if not state.last_results_feed or not hasattr(state.last_results_feed, 'entries') or not state.last_results_feed.entries:
        print("[!] No results displayed to find related work from.")
        return False

    # Parse the result number
    try:
        result_num = int(args_str)
    except ValueError:
        print("[!] Invalid number format. Usage: rel [N]")
        return False

    # Get the entry from the results
    from main import _get_entry_from_results
    entry = _get_entry_from_results(state.last_results_feed, result_num)
    if not entry:
        print(f"[!] Invalid result number: {result_num}.")
        return False

    # Get paper details for the search query
    title = entry.get('title', '').replace('\n', ' ').strip()
    authors = entry.get('authors', '')
    if isinstance(authors, list):
        authors = ', '.join([a.get('name', '') for a in authors])
    summary = entry.get('summary', '').replace('\n', ' ').strip()

    # Create a more focused search query
    if not title:
        print(f"[!] Cannot search related work for result {result_num} due to missing title.")
        return False

    # Use Gemini to extract relevant keywords for the search
    import re

    # Function to extract keywords using Gemini
    async def extract_keywords_with_gemini(title, summary, authors=None, gemini_model_name="gemini-2.5-pro-exp-03-25"):
        # Prepare the prompt for Gemini
        prompt = f"""
        I need to find related academic papers that are truly similar to the following paper. Please extract 5-7 key technical terms or phrases that would be most effective for finding closely related work in the same specific domain and application area.

        Paper Title: {title}

        Paper Summary: {summary}

        Important instructions:
        1. ALWAYS include the main domain/application area (e.g., biological tissues, cancer modeling) as one of the keywords
        2. ALWAYS include the main methodology (e.g., multi-phase field model) as one of the keywords
        3. Include specific phenomena being studied (e.g., cell migration, tissue growth)
        4. Include distinctive technical approaches unique to this paper
        5. Ensure the keywords together would find papers on very similar topics, not just general papers using similar methods

        Please format your response as a JSON array of strings containing only the keywords/phrases, like this: ["keyword1", "keyword2", ...]
        Do not include the original paper title or author names as keywords.
        """

        try:
            # Call Gemini to extract keywords
            print("[*] Using Gemini to extract relevant keywords...")

            # Use the gemini_client module to generate content
            response = await gemini_client.generate_content(prompt, model_name=gemini_model_name)

            if not response or not hasattr(response, 'text'):
                print("[!] Gemini failed to extract keywords. Falling back to rule-based extraction.")
                return None

            response_text = response.text

            # Try to parse the response as JSON
            import json
            try:
                # Extract JSON array from the response
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    keywords_json = json_match.group(0)
                    keywords = json.loads(keywords_json)
                    if isinstance(keywords, list) and len(keywords) > 0:
                        print(f"[+] Gemini extracted {len(keywords)} keywords: {', '.join(keywords)}")
                        return keywords
                print("[!] Could not parse Gemini response as JSON. Falling back to rule-based extraction.")
                return None
            except json.JSONDecodeError:
                print("[!] Failed to parse Gemini response as JSON. Falling back to rule-based extraction.")
                return None
        except Exception as e:
            print(f"[!] Error using Gemini to extract keywords: {e}")
            import traceback
            traceback.print_exc()
            return None

    # Rule-based keyword extraction as fallback
    def extract_keywords_rule_based(title, summary):
        # Remove mathematical notation which can confuse the search
        clean_title = re.sub(r'\$.*?\$', '', title)

        # Extract key phrases from the title
        key_phrases = []

        # Look for technical terms and concepts
        if 'multi-phase' in clean_title.lower() or 'multi phase' in clean_title.lower():
            key_phrases.append('"multi-phase field"')

        if 'phase change' in clean_title.lower():
            key_phrases.append('"phase change memory"')

        if 'simulation' in clean_title.lower() or 'model' in clean_title.lower():
            key_phrases.append('simulation model')

        # Extract material names if present
        if 'Ge2Sb2Te5' in title or 'GST' in title:
            key_phrases.append('Ge2Sb2Te5 OR GST')

        # If no key phrases found, extract nouns and technical terms
        if not key_phrases:
            words = re.findall(r'\b[A-Za-z][A-Za-z-]+\b', clean_title)
            # Filter out common words
            common_words = ['and', 'the', 'of', 'in', 'on', 'for', 'with', 'to', 'a', 'an']
            technical_terms = [w for w in words if w.lower() not in common_words and len(w) > 3]
            key_phrases = technical_terms[:5]

        # Add some relevant terms from the summary if available
        if summary:
            clean_summary = re.sub(r'\$.*?\$', '', summary)
            if 'method' in clean_summary.lower() and 'methodology' not in key_phrases:
                key_phrases.append('methodology')
            if 'simulation' in clean_summary.lower() and 'simulation' not in key_phrases:
                key_phrases.append('simulation')

        return key_phrases

    # Use the default Gemini model name
    gemini_model_name = "gemini-2.5-pro-exp-03-25"  # Default model

    # Extract keywords using Gemini
    keywords = await extract_keywords_with_gemini(title, summary, authors, gemini_model_name)

    # If Gemini failed, fall back to rule-based extraction
    if not keywords:
        print("[*] Using rule-based keyword extraction as fallback...")
        keywords = extract_keywords_rule_based(title, summary)

    # If we have authors, exclude them from search to avoid finding the same paper
    author_filter = ''
    if authors:
        # Get last names of first two authors
        author_names = authors.split(', ')[:2]
        last_names = [name.split()[-1] for name in author_names if name]
        if last_names:
            author_filter = ' -' + ' -'.join(last_names)  # Exclude these authors

    # Construct the search query - use a more strategic approach to keyword selection
    # We'll create multiple search strategies and try them in order
    search_strategies = []

    # Strategy 1: Use domain + methodology (typically most effective)
    domain_keyword = None
    method_keyword = None

    # Try to identify domain and method keywords from the extracted keywords
    for kw in keywords:
        kw_lower = kw.lower()
        # Look for domain/application keywords
        if any(term in kw_lower for term in ["tissue", "biolog", "cell", "cancer", "organ", "medical"]):
            domain_keyword = kw
        # Look for methodology keywords
        elif any(term in kw_lower for term in ["model", "field", "simulation", "method", "approach"]):
            method_keyword = kw

    # If we found both domain and method, create a strategy with just these two
    if domain_keyword and method_keyword:
        strategy1 = [domain_keyword, method_keyword]
        search_strategies.append(strategy1)

    # Strategy 2: Use 2-3 most important keywords
    if len(keywords) >= 2:
        strategy2 = keywords[:min(3, len(keywords))]
        search_strategies.append(strategy2)

    # Strategy 3: Use just the first keyword (most important) + a general term
    if keywords:
        strategy3 = [keywords[0]]
        # Add a general field term if not already included
        if not any(term.lower() in keywords[0].lower() for term in ["model", "simulation", "method"]):
            strategy3.append("model")
        search_strategies.append(strategy3)

    # Start with the first strategy
    print(f"[*] Using search strategy 1 of {len(search_strategies)}")
    search_keywords = search_strategies[0]

    # Add quotes around multi-word terms
    search_query = ' '.join(f'"{kw}"' if ' ' in kw else kw for kw in search_keywords) + author_filter

    # Add "related work" to encourage finding similar but different papers
    search_query += ' "related work"'

    # Add the current year to find recent related work
    import datetime
    current_year = datetime.datetime.now().year
    search_query += f' {current_year-2} OR {current_year-1} OR {current_year}'

    # Add -intitle to exclude papers with the exact same title
    if title:
        # Get the first few words of the title to exclude
        first_words = ' '.join(title.split()[:3])
        if first_words:
            search_query += f' -intitle:"{first_words}"'

    # Generated search query ready for API call

    print(f"\n[*] Finding related work for paper [{result_num}] via Serper Google Scholar")
    print(f"    Title: {title[:80]}...")
    print(f"    Authors: {authors[:80]}..." if len(authors) > 80 else f"    Authors: {authors}")

    # Add a small delay to ensure we don't hit rate limits
    time.sleep(1)

    # Call the Serper API
    serper_results = search_scholar_serper(search_query, serper_api_key)

    # Handle error cases
    if serper_results is None:
        print("[!] Error: Failed to get results from Serper API.")
        print("[!] Please check your API key and internet connection.")
        return False
    elif len(serper_results) == 0:
        # Try the other search strategies we prepared
        for strategy_index in range(1, len(search_strategies)):
            print(f"[*] No results found. Trying search strategy {strategy_index+1} of {len(search_strategies)}...")

            # Get the next strategy
            next_strategy = search_strategies[strategy_index]

            # Construct a new query with this strategy
            next_query = ' '.join(f'"{kw}"' if ' ' in kw else kw for kw in next_strategy) + author_filter
            next_query += ' "related work"'

            # Add year range for recency
            import datetime
            current_year = datetime.datetime.now().year
            next_query += f' {current_year-2} OR {current_year-1} OR {current_year}'

            print(f"[*] Trying alternative search strategy: {', '.join(next_strategy)}")

            # Call the Serper API with the new query
            serper_results = search_scholar_serper(next_query, serper_api_key)

            # If we got results, break out of the loop
            if serper_results is not None and len(serper_results) > 0:
                break

        # If we still have no results after trying all strategies, try one last approach
        if serper_results is None or len(serper_results) == 0:
            print("[*] No results with any strategy. Trying a broader approach...")

            # Use a very general query with just the domain area
            domain_terms = ["biological tissues", "cell migration", "tissue mechanics", "active matter"]
            broader_term = None

            # Find a domain term in our keywords
            for kw in keywords:
                for term in domain_terms:
                    if term.lower() in kw.lower():
                        broader_term = term
                        break
                if broader_term:
                    break

            # If no domain term found, use the first keyword
            if not broader_term and keywords:
                broader_term = keywords[0]

            # If we have a term to search with
            if broader_term:
                final_query = f'"{broader_term}" "phase field" {author_filter} "related work"'
                print(f"[*] Trying broader search with: {broader_term}")

                # Call the Serper API with the final query
                serper_results = search_scholar_serper(final_query, serper_api_key)

            # If still no results
            if serper_results is None or len(serper_results) == 0:
                print("[!] No related papers found via Serper Google Scholar.")
                return False

        # If we've reached here, we have results from one of our strategies

    # Display the results
    print("\n--- Related Papers (Google Scholar) ---")

    # Filter out the original paper if it somehow appears in results
    filtered_results = []
    for result in serper_results:
        res_title = result.get('title', 'N/A')
        # Skip if it's the same paper (simple title comparison)
        if title and res_title and title.lower().startswith(res_title.lower()[:30]) or res_title.lower().startswith(title.lower()[:30]):
            print(f"[DEBUG] Filtering out original paper: {res_title[:50]}...")
            continue
        filtered_results.append(result)

    if not filtered_results:
        print("[!] No related papers found after filtering out duplicates.")
        return False

    for i, result in enumerate(filtered_results):
        res_title = result.get('title', 'N/A')
        res_link = result.get('link', 'N/A')
        res_snippet = result.get('snippet', 'N/A').replace('\n', ' ')
        res_pub_info = result.get('publicationInformation', {})
        res_authors = res_pub_info.get('authors', [])
        res_summary = res_pub_info.get('summary', '') # Contains authors, venue, year

        print(f"\n[{i+1}] {textwrap.fill(res_title, width=80)}")
        if res_summary:
            print(f"    Info: {textwrap.fill(res_summary, width=75, subsequent_indent='          ')}")
        elif res_authors: # Fallback if summary missing
            print(f"    Authors: {', '.join(a.get('name') for a in res_authors if a.get('name'))}")

        print(f"    Link: {res_link}")
        if res_snippet != 'N/A':
            print(f"    Snippet: {textwrap.fill(res_snippet, width=70, initial_indent='             ', subsequent_indent='             ')}")

    print("-----------------------------------")
    return True
