# arXiv Gemini App - Main Application
import argparse
import os
import sys
import time
import re
import asyncio
import json
import textwrap

# Import modules from our application
import arxiv_client
import display
import gemini_client
import citation_utils
import comparison_utils
import rel_command

# For API Key loading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
ARXIV_USER_AGENT = "arXiv-Gemini-App/0.6"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
DOWNLOAD_DIR = "arxiv_downloads"

# Application state
class AppState:
    def __init__(self):
        self.current_query = ""
        self.current_start_index = 0
        self.current_max_results = 10
        self.current_sort_by = "submittedDate"
        self.current_sort_order = "descending"
        self.last_results_feed = None
        self.total_results_count = 0
        self.gemini_enabled = False
        self.serper_enabled = False
        self.downloaded_pdfs = {}
        self.gemini_uploaded_files = {}
        self.gemini_model_name = "gemini-2.5-pro-exp-03-25"


# --- Helper Functions ---
def _get_entry_from_results(results_feed, display_index):
    """Safely retrieves an entry from the last results feed by display index."""
    if not results_feed or not hasattr(results_feed, 'entries') or not results_feed.entries:
        return None
    current_page_start = int(results_feed.feed.get('opensearch_startindex', 0))
    entry_index = display_index - 1 - current_page_start
    if 0 <= entry_index < len(results_feed.entries):
        return results_feed.entries[entry_index]
    else:
        return None

async def _get_or_upload_gemini_file(pdf_filepath, state):
    """Gets existing Gemini file object or uploads if not found/inactive."""
    if pdf_filepath in state.gemini_uploaded_files:
        existing_file = state.gemini_uploaded_files[pdf_filepath]
        try:
            refreshed_file = gemini_client.genai.get_file(name=existing_file.name)
            if refreshed_file.state.name == "ACTIVE":
                print(f"[*] Using cached Gemini file object: {refreshed_file.name}")
                return refreshed_file
            else:
                print(f"[!] Cached Gemini file object ({existing_file.name}) is no longer ACTIVE (State: {refreshed_file.state.name}). Re-uploading.")
                try:
                    gemini_client.genai.delete_file(name=existing_file.name)
                except Exception: pass
        except Exception as e:
            print(f"[!] Error checking cached Gemini file status ({existing_file.name}): {e}. Re-uploading.")

    uploaded_file = await gemini_client.upload_pdf_to_gemini(pdf_filepath)
    if uploaded_file and uploaded_file.state.name == "ACTIVE":
        state.gemini_uploaded_files[pdf_filepath] = uploaded_file
        return uploaded_file
    else:
        state.gemini_uploaded_files.pop(pdf_filepath, None)
        return None

def _pretty_print_json(json_string):
    """Tries to parse and pretty-print a JSON string."""
    try:
        parsed = json.loads(json_string)
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print("[!] Could not parse JSON, printing raw output:")
        print(json_string)
    except Exception as e:
         print(f"[!] Error during JSON pretty printing: {e}")
         print(json_string)

# --- Interactive Mode ---

async def run_interactive_mode(state):
    """Runs the interactive command loop."""
    print("\n--- arXiv API Interactive Search (with Gemini Q&A/Summ/Ext & Serper Related Work) ---") # Updated Title
    print("Commands:")
    print("  q                - Query: Enter a new arXiv search query.")
    print("  n                - Next: Fetch the next page of results.")
    print("  download [N,M,..] - Download: Download PDF(s) for result number(s) N,M,... (comma-separated or single number)")
    print("")
    print("  # Commands that require downloading PDFs first:")
    print("  ask [N] \"[Q]\"    - Ask Gemini: Ask general question [Q] about PDF [N].")
    print("  ask_fig [N] \"[Q]\"  - Ask Gemini: Ask question [Q] about figure/table in PDF [N].")
    print("  sum [N] [style]  - Summarize PDF [N] using Gemini (Styles: simple, tech, key_findings).")
    print("  ext [N] [type]   - Extract structured data from PDF [N] (Types: methods, conclusion, datasets).")
    print("  compare [N1,N2..] [type] - Compare multiple papers using Gemini.")
    print("                     (types: general, methods, results, impact)")
    print("")
    print("  # Other commands:")
    print("  rel [N]          - Find related work for paper [N] using Google Scholar (Serper).")
    print("  cite [N] [format] - Export citation for paper [N] in specified format.")
    print("                     (formats: bibtex, apa, mla, chicago, ieee)")
    print("  set max [N]      - Set max results per page.")
    print("  set sort [f] [o] - Set sort order.")
    print("  set model [name] - Set Gemini model.")
    print("  show downloads   - List downloaded/uploaded PDFs.")
    print("  show model       - Show current Gemini model.")
    print("  help             - Show this help message.")
    print("  quit             - Exit.")
    print("--------------------------------------------------------------------------------")

    if not state.gemini_enabled: print("[!] Warning: Gemini API Key missing. Gemini commands disabled.")
    if not state.serper_enabled: print("[!] Warning: Serper API Key missing. 'rel' command disabled.") # Warning for Serper

    while True:
        try:
            prompt_query_part = f"Query: '{state.current_query[:30]}...' | " if state.current_query else ""
            prompt_model_part = f"Model: {state.gemini_model_name} | " if state.gemini_enabled else ""
            prompt_state = f"{prompt_query_part}Page: {state.current_start_index // state.current_max_results + 1} | Max: {state.current_max_results} | Sort: {state.current_sort_by}/{state.current_sort_order} | {prompt_model_part}"

            command_input = input(f"\n[{prompt_state}] > ").strip()
            parts = command_input.split(maxsplit=1)
            command = parts[0].lower() if parts else ""
            args_str = parts[1] if len(parts) > 1 else ""

            if command == "quit": break
            elif command == "help":
                 # Re-print help
                 print("\nCommands:")
                 print("  q                - Query: Enter a new arXiv search query.")
                 print("  n                - Next: Fetch the next page of results.")
                 print("  download [N,M,..] - Download: Download PDF(s) for result number(s) N,M,... (comma-separated or single number)")
                 print("")
                 print("  # Commands that require downloading PDFs first:")
                 print("  ask [N] \"[Q]\"    - Ask Gemini: Ask general question [Q] about PDF [N].")
                 print("  ask_fig [N] \"[Q]\"  - Ask Gemini: Ask question [Q] about figure/table in PDF [N].")
                 print("  sum [N] [style]  - Summarize PDF [N] using Gemini (Styles: simple, tech, key_findings).")
                 print("  ext [N] [type]   - Extract structured data from PDF [N] (Types: methods, conclusion, datasets).")
                 print("  compare [N1,N2..] [type] - Compare multiple papers using Gemini.")
                 print("                     (types: general, methods, results, impact)")
                 print("")
                 print("  # Other commands:")
                 print("  rel [N]          - Find related work for paper [N] using Google Scholar (Serper).") # Updated
                 print("  cite [N] [format] - Export citation for paper [N] in specified format.")
                 print("                     (formats: bibtex, apa, mla, chicago, ieee)")
                 print("  set max [N]      - Set max results per page.")
                 print("  set sort [f] [o] - Set sort order.")
                 print("  set model [name] - Set Gemini model.")
                 print("  show downloads   - List downloaded/uploaded PDFs.")
                 print("  show model       - Show current Gemini model.")
                 print("  help             - Show this help message.")
                 print("  quit             - Exit.")

            elif command == "q": # Query
                # ... (no changes needed in this block) ...
                 new_query = input("Enter new search query: ").strip()
                 if new_query:
                     state.current_query = new_query; state.current_start_index = 0
                     state.downloaded_pdfs = {}; state.gemini_uploaded_files = {}
                     state.last_results_feed = arxiv_client.search_arxiv(query=state.current_query, start=state.current_start_index, max_results=state.current_max_results, sort_by=state.current_sort_by, sort_order=state.current_sort_order)
                     if state.last_results_feed and hasattr(state.last_results_feed, 'feed'):
                         state.total_results_count = int(state.last_results_feed.feed.get('opensearch_totalresults', 0))
                         num_displayed = display.display_results(state.last_results_feed, state.current_start_index)
                         if num_displayed < state.current_max_results or state.current_start_index + num_displayed >= state.total_results_count: print("[-] Reached end of results.")
                     else: state.total_results_count = 0
                 else: print("[!] Query cannot be empty.")

            elif command == "n": # Next Page
                # ... (no changes needed in this block) ...
                 if not state.current_query: print("[!] No active query."); continue
                 if not state.last_results_feed or not hasattr(state.last_results_feed, 'entries') or not state.last_results_feed.entries: print("[-] No previous results."); continue
                 if state.current_start_index + len(state.last_results_feed.entries) >= state.total_results_count: print("[-] Already at the end."); continue
                 state.current_start_index += len(state.last_results_feed.entries)
                 state.last_results_feed = arxiv_client.search_arxiv(query=state.current_query, start=state.current_start_index, max_results=state.current_max_results, sort_by=state.current_sort_by, sort_order=state.current_sort_order)
                 if state.last_results_feed and hasattr(state.last_results_feed, 'feed'):
                      state.total_results_count = int(state.last_results_feed.feed.get('opensearch_totalresults', 0))
                      num_displayed = display.display_results(state.last_results_feed, state.current_start_index)
                      if num_displayed < state.current_max_results or state.current_start_index + num_displayed >= state.total_results_count: print("[-] Reached end of results.")
                 else: state.current_start_index -= len(state.last_results_feed.entries); state.current_start_index = max(0, state.current_start_index)

            elif command == "download" or command == "d": # Unified Download Command
                if not state.last_results_feed or not hasattr(state.last_results_feed, 'entries') or not state.last_results_feed.entries: print("[!] No results displayed."); continue
                try:
                    # Check if input is empty
                    if not args_str.strip():
                        print("[!] Missing paper number(s). Usage: download [N,M,...] (comma-separated or single number)")
                        continue

                    # Parse comma-separated list of paper numbers
                    paper_nums = [int(num.strip()) for num in args_str.split(',')]

                    # Check if the number of papers is reasonable
                    if len(paper_nums) > 20:
                        confirm = input(f"[?] You're about to download {len(paper_nums)} papers. Continue? (y/n): ").strip().lower()
                        if confirm != 'y':
                            print("[*] Download cancelled.")
                            continue

                    # Download each paper in the list
                    successful_downloads = 0
                    for num in paper_nums:
                        entry_to_download = _get_entry_from_results(state.last_results_feed, num)
                        if entry_to_download:
                            print(f"\n[*] Downloading PDF for result [{num}]...")
                            downloaded_filepath = arxiv_client.download_pdf(entry_to_download, directory=DOWNLOAD_DIR)
                            if downloaded_filepath:
                                state.downloaded_pdfs[num] = downloaded_filepath
                                successful_downloads += 1
                        else:
                            print(f"[!] Invalid result number: {num}. Skipping.")

                    if len(paper_nums) > 1:
                        print(f"\n[+] Download complete. Successfully downloaded {successful_downloads} out of {len(paper_nums)} papers.")

                except ValueError:
                    print("[!] Invalid number format. Usage: download [N,M,...] (comma-separated or single number)")
                except Exception as e:
                    print(f"[!] Error during download: {e}")

            # --- Handler for ask, ask_fig, summarize, extract (Require PDF Download & Gemini) ---
            elif command in ["ask", "ask_fig", "sum", "ext"]:
                 # ... (no changes needed in this block's logic, uses gemini_client) ...
                if not state.gemini_enabled: print(f"[!] Gemini disabled."); continue
                parts = args_str.split(maxsplit=1)
                if not parts: print(f"[!] Missing args for '{command}'."); continue
                try: result_num = int(parts[0])
                except ValueError: print(f"[!] Invalid result number '{parts[0]}'."); continue
                if result_num not in state.downloaded_pdfs: print(f"[!] PDF [{result_num}] not downloaded."); continue
                pdf_filepath = state.downloaded_pdfs[result_num]
                if not os.path.exists(pdf_filepath): print(f"[!] PDF file missing: {pdf_filepath}"); del state.downloaded_pdfs[result_num]; state.gemini_uploaded_files.pop(pdf_filepath, None); continue

                print(f"\n[*] Ensuring PDF [{result_num}] is available to Gemini...")
                uploaded_file = await _get_or_upload_gemini_file(pdf_filepath, state)
                if not uploaded_file: print("[!] PDF upload/retrieval failed."); continue

                gemini_response = None
                action_description = f"processing {command}"
                if command in ["ask", "ask_fig"]:
                    match = re.match(r'^\s*"(.*?)"\s*$', parts[1] if len(parts) > 1 else ""); usage = f"{command} [N] \"[Question]\""
                    if not match: print(f"[!] Invalid format. Usage: {usage}"); continue
                    question = match.group(1); is_figure_query = (command == "ask_fig"); action_description = f"asking about {'figures ' if is_figure_query else ''}PDF: '{question[:40]}...'"
                    print(f"[*] {action_description}")
                    gemini_response = await gemini_client.ask_question_about_pdf(uploaded_file, question, model_name=state.gemini_model_name)
                elif command == "sum":
                    style = parts[1].strip().lower() if len(parts) > 1 else "default"; valid_styles = ["default", "simple", "technical", "key_findings", "eli5"]
                    if style not in valid_styles: print(f"[!] Invalid style '{style}'. Valid: {', '.join(valid_styles)}"); continue
                    action_description = f"summarizing PDF (Style: {style})"
                    print(f"[*] {action_description}")
                    gemini_response = await gemini_client.summarize_or_explain_pdf(uploaded_file, "summarize", style, model_name=state.gemini_model_name)
                elif command == "ext":
                    if len(parts) < 2 or not parts[1].strip(): print("[!] Missing extraction type."); print(f"    Available types: {', '.join(gemini_client.EXTRACTION_SCHEMAS.keys())}"); continue
                    schema_key = parts[1].strip().lower()
                    if schema_key not in gemini_client.EXTRACTION_SCHEMAS: print(f"[!] Invalid extraction type '{schema_key}'. Available: {', '.join(gemini_client.EXTRACTION_SCHEMAS.keys())}"); continue
                    action_description = f"extracting '{schema_key}' as JSON"
                    print(f"[*] {action_description}")
                    gemini_response = await gemini_client.extract_structured_data(uploaded_file, schema_key, model_name=state.gemini_model_name)

                print(f"\n--- Gemini Response ({action_description}) ---")
                if gemini_response:
                    if command == "ext": _pretty_print_json(gemini_response)
                    else: print(gemini_response)
                else: print(f"[!] Gemini failed to provide a response for '{command}'.")
                print("------------------------------------------")


            # --- MODIFIED Handler for related (Uses Serper) ---
            elif command == "rel": # Find related work via Serper
                # Use our new rel_command module to handle the command
                if not await rel_command.handle_rel_command(args_str, state, SERPER_API_KEY):
                    continue

            # --- Handler for citation export ---
            elif command == "cite": # Export citation
                if not state.last_results_feed or not hasattr(state.last_results_feed, 'entries') or not state.last_results_feed.entries:
                    print("[!] No results displayed to generate citation from.")
                    continue

                parts = args_str.split(maxsplit=1)
                if not parts:
                    print("[!] Missing arguments. Usage: cite [N] [format]")
                    continue

                try:
                    result_num = int(parts[0])
                except ValueError:
                    print(f"[!] Invalid result number '{parts[0]}'. Usage: cite [N] [format]")
                    continue

                # Get the citation format
                citation_format = parts[1].lower() if len(parts) > 1 else "bibtex"
                if citation_format not in citation_utils.CITATION_FORMATS:
                    print(f"[!] Invalid citation format '{citation_format}'. Available formats: {', '.join(citation_utils.CITATION_FORMATS)}")
                    continue

                # Get the entry
                entry = _get_entry_from_results(state.last_results_feed, result_num)
                if not entry:
                    print(f"[!] Invalid result number: {result_num}.")
                    continue

                # Generate the citation
                print(f"\n--- Citation for [{result_num}] in {citation_format.upper()} format ---")
                citation = citation_utils.format_citation(entry, citation_format)
                print(citation)
                print("-----------------------------------")

            # --- Handler for paper comparison ---
            elif command == "compare": # Compare papers
                if not state.gemini_enabled:
                    print(f"[!] Gemini disabled. Cannot use '{command}'.")
                    continue

                parts = args_str.split(maxsplit=1)
                if not parts:
                    print("[!] Missing arguments. Usage: compare [N1,N2,...] [type]")
                    continue

                # Parse the paper numbers
                try:
                    paper_nums = [int(num.strip()) for num in parts[0].split(',')]
                    if len(paper_nums) < 2:
                        print("[!] At least two paper numbers are required for comparison.")
                        continue
                except ValueError:
                    print(f"[!] Invalid paper number format. Usage: compare [N1,N2,...] [type]")
                    continue

                # Get the comparison type
                comparison_type = parts[1].lower() if len(parts) > 1 else "general"
                if comparison_type not in comparison_utils.COMPARISON_TYPES:
                    print(f"[!] Invalid comparison type '{comparison_type}'. Available types: {', '.join(comparison_utils.COMPARISON_TYPES.keys())}")
                    continue

                # Check if all papers are downloaded
                missing_papers = [num for num in paper_nums if num not in state.downloaded_pdfs]
                if missing_papers:
                    print(f"[!] The following papers are not downloaded: {missing_papers}")
                    print("    Please download all papers first using 'd [N]'.")
                    continue

                # Get file objects for all papers
                file_objects = []
                for paper_num in paper_nums:
                    pdf_filepath = state.downloaded_pdfs[paper_num]
                    if not os.path.exists(pdf_filepath):
                        print(f"[!] PDF file missing: {pdf_filepath}")
                        del state.downloaded_pdfs[paper_num]
                        state.gemini_uploaded_files.pop(pdf_filepath, None)
                        continue

                    print(f"\n[*] Ensuring PDF [{paper_num}] is available to Gemini...")
                    uploaded_file = await _get_or_upload_gemini_file(pdf_filepath, state)
                    if not uploaded_file:
                        print(f"[!] PDF upload/retrieval failed for paper {paper_num}.")
                        continue

                    file_objects.append(uploaded_file)

                if len(file_objects) < 2:
                    print("[!] At least two valid PDF files are required for comparison.")
                    continue

                # Perform the comparison
                print(f"\n[*] Comparing {len(file_objects)} papers (Type: {comparison_type})...")
                comparison_result = await gemini_client.compare_papers(file_objects, comparison_type, model_name=state.gemini_model_name)

                print(f"\n--- Paper Comparison ({comparison_type.upper()}) ---")
                if comparison_result:
                    print(comparison_result)
                else:
                    print("[!] Gemini failed to provide a comparison analysis.")
                print("------------------------------------------")

            # --- MODIFIED Handler for related (Uses Serper) ---
            elif command == "rel": # Find related work via Serper
                if not state.serper_enabled: # Check if Serper key is available
                    print(f"[!] Serper API not configured. Cannot use '{command}'.")
                    print("[!] To enable this feature, please set the SERPER_API_KEY environment variable.")
                    print("[!] You can get a free API key from https://serper.dev/")
                    continue
                if not state.last_results_feed or not hasattr(state.last_results_feed, 'entries') or not state.last_results_feed.entries:
                    print("[!] No results displayed to find related work from.")
                    continue
                try:
                    result_num = int(args_str)
                except ValueError:
                    print("[!] Invalid number format. Usage: rel [N]")
                    continue

                entry = _get_entry_from_results(state.last_results_feed, result_num)
                if not entry:
                    print(f"[!] Invalid result number: {result_num}.")
                    continue

                print("[DEBUG] Getting paper details for search query")
                # Get paper details for the search query
                title = entry.get('title', '').replace('\n', ' ').strip()
                authors = entry.get('authors', '')
                if isinstance(authors, list):
                    authors = ', '.join([a.get('name', '') for a in authors])
                summary = entry.get('summary', '').replace('\n', ' ').strip()
                print(f"[DEBUG] Title: {title[:40]}...")
                print(f"[DEBUG] Authors: {authors[:40]}..." if len(authors) > 40 else f"[DEBUG] Authors: {authors}")

                # Create a more focused search query
                if not title:
                    print(f"[!] Cannot search related work for result {result_num} due to missing title.")
                    continue

                # Extract keywords from title and summary for a better search
                search_query = title
                if len(summary) > 100:  # If we have a substantial summary, use it to enhance the query
                    # Take the first 200 chars of summary to focus on the introduction/problem statement
                    search_query = f"{title} {summary[:200]}"
                print(f"[DEBUG] Search query: {search_query[:60]}...")

                print(f"\n[*] Finding related work for paper [{result_num}] via Serper Google Scholar")
                print(f"    Title: {title[:80]}...")
                print(f"    Authors: {authors[:80]}..." if len(authors) > 80 else f"    Authors: {authors}")

                # Call the function in rel_command (passing the Serper key)
                try:
                    print(f"[DEBUG] Calling Serper API with query: {search_query[:40]}...")
                    # Add a small delay to ensure we don't hit rate limits
                    import time
                    time.sleep(1)

                    # Call the Serper API with detailed debugging
                    serper_results = gemini_client.search_scholar_serper(search_query, SERPER_API_KEY) # Pass the key
                    print(f"[DEBUG] Serper API returned: {type(serper_results)} with {len(serper_results) if serper_results else 0} results")

                    # Handle error cases
                    if serper_results is None:
                        print("[!] Error: Failed to get results from Serper API.")
                        print("[!] Please check your API key and internet connection.")
                        continue
                    elif len(serper_results) == 0:
                        print("[!] No related papers found via Serper Google Scholar.")
                        continue
                except Exception as e:
                    print(f"[!] Error calling Serper API: {e}")
                    print("[!] Please check your API key and internet connection.")
                    import traceback
                    traceback.print_exc()
                    continue

                print("[DEBUG] About to display Serper results")
                print("\n--- Serper Google Scholar Results ---")
                if serper_results is not None and len(serper_results) > 0:
                    print(f"[DEBUG] Found {len(serper_results)} results to display")
                    for i, result in enumerate(serper_results):
                        print(f"[DEBUG] Processing result {i+1}")
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
                else:
                    print("[DEBUG] No results to display")
                    print("-" * 40)
                print("-----------------------------------")
                print("[DEBUG] Finished displaying Serper results")


            elif command == "show": # Settings or Downloads
                 # ... (no changes needed in this block, except maybe the 'show model' output) ...
                 sub_command = args_str.lower()
                 if sub_command == "downloads":
                     print("\n--- Downloaded PDFs (Current Session) ---")
                     if state.downloaded_pdfs:
                         for idx, path in sorted(state.downloaded_pdfs.items()):
                             status = "[OK]" if os.path.exists(path) else "[Missing!]"
                             gemini_status = "[Uploaded]" if path in state.gemini_uploaded_files else "[Not Uploaded]"
                             print(f"  [{idx}]: {path} {status} {gemini_status}")
                     else: print("  No PDFs downloaded yet."); print("-----------------------------------------")
                 elif sub_command == "model": print(f"[*] Current Gemini model: {state.gemini_model_name}")
                 else: print("[!] Unknown 'show' command. Try 'downloads' or 'model'.")

            elif command == "set": # Settings
                 # ... (keep max, sort logic; update model logic slightly if desired) ...
                 set_parts = args_str.split(maxsplit=1)
                 if len(set_parts) < 2: print("[!] Usage: set [max|sort|model] [value(s)]"); continue
                 setting = set_parts[0].lower(); value_str = set_parts[1]
                 if setting == "max":
                     try: new_max = int(value_str); state.current_max_results = max(1, min(2000, new_max)); print(f"[*] Max results set to {state.current_max_results}."); state.current_start_index = 0
                     except ValueError: print("[!] Invalid number for max.")
                 elif setting == "sort":
                     # ... sort logic unchanged ...
                     sort_value_parts = value_str.split(); api_field_name = None; matched_order = None
                     if len(sort_value_parts) == 2:
                         field, order = sort_value_parts[0].lower(), sort_value_parts[1].lower()
                         valid_fields = ["relevance", "lastupdateddate", "submitteddate"]; valid_orders = ["ascending", "descending"]
                         matched_field = next((f for f in valid_fields if f.startswith(field)), None); matched_order = next((o for o in valid_orders if o.startswith(order)), None)
                         if matched_field and matched_order: api_field_name = matched_field.replace("lastupdateddate", "lastUpdatedDate").replace("submitteddate", "submittedDate")
                     if api_field_name and matched_order: state.current_sort_by = api_field_name; state.current_sort_order = matched_order; print(f"[*] Sort order set."); state.current_start_index = 0
                     else: print("[!] Invalid sort field/order. Usage: set sort [field] [order]")
                 elif setting == "model":
                      new_model = value_str.strip()
                      if new_model: state.gemini_model_name = new_model; print(f"[*] Gemini model set to: {state.gemini_model_name}")
                      else: print("[!] Model name cannot be empty.")
                 else: print(f"[!] Unknown setting '{setting}'. Use 'max', 'sort', or 'model'.")

            elif not command: pass # Empty input
            else: print(f"[!] Unknown command: '{command}'. Type 'help'.")

        except KeyboardInterrupt: print("\n[!] Interrupt received."); break
        except EOFError: print("\n[!] EOF received."); break
        except Exception as e: print(f"\n[!] Unexpected error: {e}"); import traceback; traceback.print_exc()


# --- Main Execution ---

async def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Search arXiv, interact with Gemini & Serper Scholar.") # Updated desc
    # ... (keep existing args: q, m, s, sort-by, sort-order, download, download-dir, ask, ask-fig, summarize, extract) ...
    parser.add_argument("-q", "--query", type=str, help="arXiv search query (non-interactive mode)")
    parser.add_argument("-m", "--max-results", type=int, default=10, help="Max results per page (default: 10)")
    parser.add_argument("-s", "--start", type=int, default=0, help="Starting index for results (default: 0)")
    parser.add_argument("--sort-by", type=str, default="submittedDate", choices=['relevance', 'lastUpdatedDate', 'submittedDate'], help="Field to sort by")
    parser.add_argument("--sort-order", type=str, default="descending", choices=['ascending', 'descending'], help="Sort order")
    parser.add_argument("--download", metavar='N,M,...', type=str, help="Download PDF(s) for result number(s) N,M,... (comma-separated or single number, requires --query).")
    parser.add_argument("--download-dir", type=str, default=DOWNLOAD_DIR, help=f"PDF download directory (default: {DOWNLOAD_DIR}).")
    parser.add_argument("--ask", metavar='"Q"', type=str, help="Ask Gemini question Q about PDF N (requires --query & --download N).")
    parser.add_argument("--ask-fig", metavar='"Q"', type=str, help="Ask Gemini Q about figures in PDF N (req --query & --download N).")
    parser.add_argument("--summarize", metavar='N [style]', nargs='+', help="Summarize PDF N [style] (req --query & --download N).")
    parser.add_argument("--extract", metavar='N type', nargs=2, help="Extract type from PDF N (req --query & --download N).")
    parser.add_argument("--related", metavar='N', type=int, help="Find Scholar results related to paper N (requires --query & SERPER_API_KEY).") # Updated help
    parser.add_argument("--cite", metavar='N format', nargs=2, help="Export citation for paper N in specified format (requires --query).")
    parser.add_argument("--compare", metavar='N1,N2,... type', nargs=2, help="Compare papers (requires --query & downloading papers).")
    parser.add_argument("--model", type=str, help="Specify Gemini model to use (e.g., gemini-2.5-pro-exp-03-25).")

    args = parser.parse_args()

    # --- App State and API Config ---
    app_state = AppState()
    app_state.current_max_results = args.max_results
    app_state.current_sort_by = args.sort_by
    app_state.current_sort_order = args.sort_order
    if args.model: app_state.gemini_model_name = args.model

    # Configure Gemini
    if GEMINI_API_KEY:
        if gemini_client.configure_gemini(GEMINI_API_KEY): app_state.gemini_enabled = True
        else: print("[!] Failed Gemini config."); app_state.gemini_enabled = False
    else: print("[!] GEMINI_API_KEY not set."); app_state.gemini_enabled = False

    # Configure Serper
    if SERPER_API_KEY:
        print("[*] Serper API Key found. Testing connection...")
        try:
            # Make a simple test query to verify the API key works
            test_results = gemini_client.search_scholar_serper("test query", SERPER_API_KEY, num_results=1)
            if test_results is not None:
                print("[*] Serper API connection successful.")
                app_state.serper_enabled = True
            else:
                print("[!] Serper API test failed. 'related' feature disabled.")
                print("[!] Please check your API key and internet connection.")
                app_state.serper_enabled = False
        except Exception as e:
            print(f"[!] Error testing Serper API: {e}")
            print("[!] 'related' feature disabled.")
            app_state.serper_enabled = False
    else:
        print("[!] SERPER_API_KEY not set. 'related' feature disabled.")
        print("[!] To enable the 'related' feature, please set the SERPER_API_KEY environment variable.")
        print("[!] You can get a free API key from https://serper.dev/")
        app_state.serper_enabled = False


    # --- Non-Interactive Mode ---
    if args.query:
        print("[*] Running in non-interactive mode...")
        app_state.current_query = args.query
        results_feed = arxiv_client.search_arxiv(query=args.query, start=args.start, max_results=args.max_results, sort_by=args.sort_by, sort_order=args.sort_order)
        num_displayed = display.display_results(results_feed, args.start)

        pdf_filepath_action = None; entry_action = None; result_num_action = None

        # --- Download Prerequisite Check ---
        action_target_num_pdf = None
        if args.download:
            # If download is specified, use the first number in the list
            try:
                if ',' in args.download:
                    action_target_num_pdf = int(args.download.split(',')[0].strip())
                else:
                    action_target_num_pdf = int(args.download)
            except ValueError:
                print("[!] Invalid download number format.")

        # Override with specific action targets if provided
        if args.summarize: action_target_num_pdf = int(args.summarize[0])
        if args.extract: action_target_num_pdf = int(args.extract[0])

        # For ask/ask_fig, we need to ensure a PDF is downloaded
        if (args.ask or args.ask_fig) and action_target_num_pdf is None:
            print("[!] Error: --ask and --ask_fig require specifying a PDF with --download")

        if action_target_num_pdf is not None and (args.ask or args.ask_fig or args.summarize or args.extract):
             if results_feed and hasattr(results_feed, 'entries') and results_feed.entries:
                 entry_action = _get_entry_from_results(results_feed, action_target_num_pdf)
                 if entry_action:
                     print(f"[*] Checking/Downloading PDF for result [{action_target_num_pdf}]...")
                     pdf_filepath_action = arxiv_client.download_pdf(entry_action, directory=args.download_dir)
                     if pdf_filepath_action: result_num_action = action_target_num_pdf
                     else: print(f"[!] Failed PDF download for result {action_target_num_pdf}.")
                 else: print(f"[!] Target index {action_target_num_pdf} out of range.")
             else: print("[!] Cannot download, no results found.")
        elif args.download is not None: # Handle simple --download N
             if results_feed and hasattr(results_feed, 'entries') and results_feed.entries:
                  entry_d = _get_entry_from_results(results_feed, args.download)
                  if entry_d: arxiv_client.download_pdf(entry_d, directory=args.download_dir)
                  else: print(f"[!] Target index {args.download} out of range.")
             else: print("[!] Cannot download, no results found.")

        elif args.batch_download is not None: # Handle batch download
             if results_feed and hasattr(results_feed, 'entries') and results_feed.entries:
                  # Parse the range (e.g., "1-5")
                  range_match = re.match(r'^(\d+)-(\d+)$', args.batch_download)
                  if not range_match:
                      print("[!] Invalid range format for --batch-download. Use format N1-N2 (e.g., 1-5)")
                  else:
                      start_num = int(range_match.group(1))
                      end_num = int(range_match.group(2))

                      if start_num > end_num:
                          print("[!] Invalid range: start number must be less than or equal to end number.")
                      else:
                          # Download each paper in the range
                          successful_downloads = 0
                          for num in range(start_num, end_num + 1):
                              entry_to_download = _get_entry_from_results(results_feed, num)
                              if entry_to_download:
                                  print(f"\n[*] Downloading PDF for result [{num}]...")
                                  downloaded_filepath = arxiv_client.download_pdf(entry_to_download, directory=args.download_dir)
                                  if downloaded_filepath:
                                      app_state.downloaded_pdfs[num] = downloaded_filepath
                                      successful_downloads += 1
                              else:
                                  print(f"[!] Invalid result number: {num}. Skipping.")

                          print(f"\n[+] Download complete. Successfully downloaded {successful_downloads} out of {len(paper_nums)} papers.")
             else: print("[!] Cannot download, no results found.")

        # --- Perform Actions (Non-Interactive) ---
        gemini_action_requested = args.ask or args.ask_fig or args.summarize or args.extract
        serper_action_requested = args.related is not None
        citation_action_requested = args.cite is not None
        comparison_action_requested = args.compare is not None

        # Gemini PDF Actions
        if gemini_action_requested:
            if not app_state.gemini_enabled: print("[!] Cannot perform Gemini action: API not configured.")
            elif not pdf_filepath_action: print("[!] Cannot perform Gemini action: PDF download failed or required index not provided via --download.")
            else:
                print(f"\n[*] Ensuring PDF [{result_num_action}] is available to Gemini...")
                uploaded_file = await _get_or_upload_gemini_file(pdf_filepath_action, app_state)
                if uploaded_file:
                    gemini_response = None; action_description = "processing Gemini request"
                    if args.ask_fig: question = args.ask_fig; action_description = f"asking about figures: '{question[:40]}...'"; gemini_response = await gemini_client.ask_question_about_pdf(uploaded_file, question, model_name=app_state.gemini_model_name)
                    elif args.ask: question = args.ask; action_description = f"asking: '{question[:40]}...'"; gemini_response = await gemini_client.ask_question_about_pdf(uploaded_file, question, model_name=app_state.gemini_model_name)
                    elif args.summarize: style = args.summarize[1].lower() if len(args.summarize) > 1 else "default"; action_description = f"summarizing (Style: {style})"; gemini_response = await gemini_client.summarize_or_explain_pdf(uploaded_file, "summarize", style, model_name=app_state.gemini_model_name)
                    elif args.extract: schema_key = args.extract[1].lower(); action_description = f"extracting '{schema_key}'"; gemini_response = await gemini_client.extract_structured_data(uploaded_file, schema_key, model_name=app_state.gemini_model_name)

                    if gemini_response is not None:
                        print(f"\n--- Gemini Response ({action_description}) ---");
                        if args.extract: _pretty_print_json(gemini_response)
                        else: print(gemini_response); print("------------------------------------------")
                    else: print(f"[!] Gemini failed response for {action_description}.")
                else: print("[!] PDF upload/retrieval failed for Gemini action.")

        # Serper Related Action
        if serper_action_requested:
             if not app_state.serper_enabled: print("[!] Cannot find related work: Serper API not configured.")
             else:
                  result_num_rel = args.related
                  entry_rel = _get_entry_from_results(results_feed, result_num_rel)
                  if entry_rel:
                      title = entry_rel.get('title','').replace('\n',' ').strip()
                      if title:
                          print(f"\n[*] Finding related work for [{result_num_rel}] via Serper: '{title[:60]}...'")
                          serper_results = gemini_client.search_scholar_serper(title, SERPER_API_KEY)
                          print("\n--- Serper Google Scholar Results ---")
                          if serper_results is not None and len(serper_results) > 0:
                              for i, result in enumerate(serper_results):
                                  # ... (formatting logic as in interactive mode) ...
                                  res_title = result.get('title', 'N/A'); res_link = result.get('link', 'N/A')
                                  res_snippet = result.get('snippet', 'N/A').replace('\n', ' ')
                                  res_pub_info = result.get('publicationInformation', {})
                                  res_summary = res_pub_info.get('summary', '')
                                  print(f"\n[{i+1}] {textwrap.fill(res_title, width=80)}")
                                  if res_summary: print(f"    Info: {textwrap.fill(res_summary, width=75, subsequent_indent='          ')}")
                                  print(f"    Link: {res_link}")
                                  if res_snippet != 'N/A': print(f"    Snippet: {textwrap.fill(res_snippet, width=70, initial_indent='             ', subsequent_indent='             ')}")
                                  print("-" * 40)
                          elif serper_results is not None: print("[-] No results found via Serper.")
                          else: print("[!] Serper API failed.")
                          print("-----------------------------------")
                      else: print(f"[!] Missing title for result {result_num_rel}.")
                  else: print(f"[!] Invalid index for --related: {result_num_rel}.")

        # Citation Action
        if citation_action_requested:
            result_num_cite = int(args.cite[0])
            citation_format = args.cite[1].lower()

            if citation_format not in citation_utils.CITATION_FORMATS:
                print(f"[!] Invalid citation format '{citation_format}'. Available formats: {', '.join(citation_utils.CITATION_FORMATS)}")
            else:
                entry_cite = _get_entry_from_results(results_feed, result_num_cite)
                if entry_cite:
                    print(f"\n--- Citation for [{result_num_cite}] in {citation_format.upper()} format ---")
                    citation = citation_utils.format_citation(entry_cite, citation_format)
                    print(citation)
                    print("-----------------------------------")
                else:
                    print(f"[!] Invalid index for --cite: {result_num_cite}.")

        # Paper Comparison Action
        if comparison_action_requested:
            if not app_state.gemini_enabled:
                print("[!] Cannot perform paper comparison: Gemini API not configured.")
            else:
                paper_nums_str = args.compare[0]
                comparison_type = args.compare[1].lower()

                # Parse paper numbers
                try:
                    paper_nums = [int(num.strip()) for num in paper_nums_str.split(',')]
                    if len(paper_nums) < 2:
                        print("[!] At least two paper numbers are required for comparison.")
                except ValueError:
                    print(f"[!] Invalid paper number format in '{paper_nums_str}'. Use comma-separated numbers.")
                    paper_nums = []

                # Check comparison type
                if comparison_type not in comparison_utils.COMPARISON_TYPES:
                    print(f"[!] Invalid comparison type '{comparison_type}'. Available types: {', '.join(comparison_utils.COMPARISON_TYPES.keys())}")
                elif paper_nums:
                    # Download papers if needed
                    file_objects = []
                    for paper_num in paper_nums:
                        entry = _get_entry_from_results(results_feed, paper_num)
                        if not entry:
                            print(f"[!] Invalid paper index: {paper_num}")
                            continue

                        # Download the PDF if not already downloaded
                        pdf_filepath = None
                        for result_key, path in app_state.downloaded_pdfs.items():
                            if result_key == paper_num:
                                pdf_filepath = path
                                break

                        if not pdf_filepath:
                            print(f"[*] Downloading PDF for paper [{paper_num}]...")
                            pdf_filepath = arxiv_client.download_pdf(entry, directory=args.download_dir)
                            if pdf_filepath:
                                app_state.downloaded_pdfs[paper_num] = pdf_filepath
                            else:
                                print(f"[!] Failed to download PDF for paper {paper_num}")
                                continue

                        # Upload to Gemini
                        print(f"[*] Ensuring PDF [{paper_num}] is available to Gemini...")
                        uploaded_file = await _get_or_upload_gemini_file(pdf_filepath, app_state)
                        if uploaded_file:
                            file_objects.append(uploaded_file)
                        else:
                            print(f"[!] Failed to upload PDF for paper {paper_num} to Gemini")

                    # Perform comparison if we have enough papers
                    if len(file_objects) >= 2:
                        print(f"\n[*] Comparing {len(file_objects)} papers (Type: {comparison_type})...")
                        comparison_result = await gemini_client.compare_papers(file_objects, comparison_type, model_name=app_state.gemini_model_name)

                        print(f"\n--- Paper Comparison ({comparison_type.upper()}) ---")
                        if comparison_result:
                            print(comparison_result)
                        else:
                            print("[!] Gemini failed to provide a comparison analysis.")
                        print("------------------------------------------")
                    else:
                        print("[!] Not enough valid papers available for comparison (minimum 2 required).")

    # --- Interactive Mode ---
    else:
        if args.download or args.ask or args.ask_fig or args.summarize or args.extract or args.related or args.cite or args.compare:
            print("[!] Warning: Action flags require --query. Ignored.")
        await run_interactive_mode(app_state)

    print("\n[*] Exiting arXiv search tool.")


if __name__ == "__main__":
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())