import textwrap
import os

def display_results(feed, start_index=0):
    """
    Displays the search results in a readable format.

    Args:
        feed (feedparser.FeedParserDict): The parsed feed data.
        start_index (int): The starting index of the results displayed (for numbering).

    Returns:
        int: The number of results displayed.
    """
    if not feed or not hasattr(feed, 'entries') or not feed.entries:
        # Check total results to differentiate no match vs end of pages
        total_results_str = feed.feed.get('opensearch_totalresults', '0') if feed and hasattr(feed, 'feed') else '0'
        try:
            total_results = int(total_results_str)
            if total_results > 0 and start_index > 0 :
                print("[-] No more results found.")
            else:
                 print("[-] No results found for this query.")
        except ValueError:
            print("[-] No results found (could not parse total results).")
        return 0

    total_results = feed.feed.get('opensearch_totalresults', 'Unknown')
    items_per_page = feed.feed.get('opensearch_itemsperpage', len(feed.entries))
    current_start = feed.feed.get('opensearch_startindex', start_index)

    print(f"\n--- Results {int(current_start) + 1} - {int(current_start) + len(feed.entries)} (Total Found: {total_results}) ---")

    for i, entry in enumerate(feed.entries):
        display_index = int(current_start) + i + 1
        title = entry.get('title', 'N/A').replace('\n', ' ').strip()
        arxiv_id = entry.get('id', 'N/A').split('/abs/')[-1] # Extract ID from URL
        published_date = entry.get('published', 'N/A')
        updated_date = entry.get('updated', 'N/A')
        summary = entry.get('summary', 'N/A').replace('\n', ' ').strip()

        # Get authors nicely
        authors = ', '.join(author.get('name', 'Unknown Author') for author in entry.get('authors', []))

        # Get PDF link
        pdf_link = 'N/A'
        for link in entry.get('links', []):
            if link.get('title') == 'pdf': # More reliable check than type sometimes
                pdf_link = link.get('href', 'N/A')
                break
            elif link.get('type') == 'application/pdf': # Fallback check
                 pdf_link = link.get('href', 'N/A')
                 # Don't break here, title='pdf' is preferred

        # Get categories
        primary_category = entry.get('arxiv_primary_category', {}).get('term', 'N/A')
        all_categories = [cat.get('term', '') for cat in entry.get('tags', [])] # feedparser uses 'tags'

        # Get DOI and Journal Ref (handle missing attributes)
        doi = entry.get('arxiv_doi', 'N/A')
        journal_ref = entry.get('arxiv_journal_ref', 'N/A')

        print(f"\n[{display_index}] ID: {arxiv_id} (Primary Cat: {primary_category})")
        print(f"    Title: {textwrap.fill(title, width=80, subsequent_indent='           ')}")
        print(f"    Authors: {textwrap.fill(authors, width=75, subsequent_indent='             ')}")
        print(f"    Published: {published_date}")
        if updated_date != published_date:
             print(f"    Updated: {updated_date}")
        print(f"    Categories: {', '.join(filter(None, all_categories))}") # Filter out empty strings if any
        if doi != 'N/A':
            print(f"    DOI: {doi}")
        if journal_ref != 'N/A':
            print(f"    Journal Ref: {journal_ref}")
        print(f"    Abstract Link: {entry.get('link', 'N/A')}") # Link to abstract page
        print(f"    PDF Link: {pdf_link}")
        print(f"    Summary: {textwrap.fill(summary, width=75, initial_indent='             ', subsequent_indent='             ')[:400]}...") # Limit summary length
        print("-" * 80)

    return len(feed.entries)