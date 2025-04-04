"""
Citation utilities for the arXiv Gemini App.
Provides functions to format arXiv entries in various citation styles.
"""

import re
from datetime import datetime

# Citation format constants
CITATION_FORMATS = ["bibtex", "apa", "mla", "chicago", "ieee"]

def format_citation(entry, format_type="bibtex"):
    """
    Format an arXiv entry in the specified citation style.
    
    Args:
        entry (feedparser.FeedParserDict.entry): The parsed entry data.
        format_type (str): The citation format to use (bibtex, apa, mla, chicago, ieee).
        
    Returns:
        str: The formatted citation.
    """
    if format_type.lower() not in CITATION_FORMATS:
        return f"Error: Unsupported citation format '{format_type}'. Supported formats: {', '.join(CITATION_FORMATS)}"
    
    # Extract common information needed for citations
    try:
        # Basic paper information
        title = entry.get('title', 'Unknown Title').replace('\n', ' ').strip()
        arxiv_id = entry.get('id', '').split('/abs/')[-1]  # e.g., 1707.08567v1
        arxiv_url = entry.get('link', f"https://arxiv.org/abs/{arxiv_id}")
        
        # Author information
        authors = [author.get('name', 'Unknown Author') for author in entry.get('authors', [])]
        
        # Date information
        published_date = entry.get('published', '')
        updated_date = entry.get('updated', '')
        
        # Try to parse the date
        try:
            # arXiv dates are typically in format: 2023-01-15T12:34:56Z
            pub_date = datetime.strptime(published_date, "%Y-%m-%dT%H:%M:%SZ")
            pub_year = pub_date.year
            pub_month = pub_date.month
            pub_month_name = pub_date.strftime("%B")
        except (ValueError, TypeError):
            # Fallback if date parsing fails
            pub_year = published_date.split('-')[0] if '-' in published_date else 'Unknown Year'
            pub_month = 1
            pub_month_name = "January"
        
        # Additional metadata
        doi = entry.get('arxiv_doi', '')
        journal_ref = entry.get('arxiv_journal_ref', '')
        primary_category = entry.get('arxiv_primary_category', {}).get('term', '')
        categories = [cat.get('term', '') for cat in entry.get('tags', [])]
        summary = entry.get('summary', '').replace('\n', ' ').strip()
        
        # Format based on the requested citation style
        if format_type.lower() == "bibtex":
            return format_bibtex(arxiv_id, title, authors, pub_year, pub_month, arxiv_url, doi, journal_ref, primary_category, summary)
        elif format_type.lower() == "apa":
            return format_apa(title, authors, pub_year, pub_month_name, arxiv_url, doi, journal_ref)
        elif format_type.lower() == "mla":
            return format_mla(title, authors, pub_year, arxiv_url)
        elif format_type.lower() == "chicago":
            return format_chicago(title, authors, pub_year, pub_month_name, arxiv_url, doi)
        elif format_type.lower() == "ieee":
            return format_ieee(title, authors, pub_year, pub_month, arxiv_url, doi, journal_ref)
        
    except Exception as e:
        return f"Error generating citation: {str(e)}"


def format_bibtex(arxiv_id, title, authors, year, month, url, doi, journal_ref, category, abstract):
    """Format citation in BibTeX style."""
    # Clean the arXiv ID for use as a citation key
    clean_id = re.sub(r'[^a-zA-Z0-9]', '', arxiv_id)
    
    # Format authors for BibTeX
    if authors:
        author_str = " and ".join(authors)
    else:
        author_str = "Unknown Author"
    
    # Start building the BibTeX entry
    bibtex = [
        f"@article{{{clean_id},",
        f"  title = {{{title}}},",
        f"  author = {{{author_str}}},",
        f"  year = {{{year}}},",
        f"  month = {{{month}}},",
        f"  eprint = {{{arxiv_id}}},",
        f"  archivePrefix = {{arXiv}},",
        f"  primaryClass = {{{category}}},",
    ]
    
    # Add optional fields if available
    if doi:
        bibtex.append(f"  doi = {{{doi}}},")
    if journal_ref:
        bibtex.append(f"  journal = {{{journal_ref}}},")
    if url:
        bibtex.append(f"  url = {{{url}}},")
    if abstract:
        # Limit abstract length for BibTeX
        short_abstract = abstract[:500] + "..." if len(abstract) > 500 else abstract
        bibtex.append(f"  abstract = {{{short_abstract}}},")
    
    # Close the BibTeX entry
    bibtex.append("}")
    
    return "\n".join(bibtex)


def format_apa(title, authors, year, month, url, doi, journal_ref):
    """Format citation in APA style."""
    # Format authors for APA
    if authors:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} & {authors[1]}"
        else:
            author_str = f"{authors[0]} et al."
    else:
        author_str = "Unknown Author"
    
    # Build the APA citation
    apa = f"{author_str}. ({year}). {title}."
    
    # Add journal reference if available
    if journal_ref:
        apa += f" {journal_ref}."
    else:
        apa += f" arXiv preprint."
    
    # Add DOI or URL
    if doi:
        apa += f" https://doi.org/{doi}"
    elif url:
        apa += f" Retrieved from {url}"
    
    return apa


def format_mla(title, authors, year, url):
    """Format citation in MLA style."""
    # Format authors for MLA
    if authors:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} and {authors[1]}"
        else:
            author_str = f"{authors[0]} et al."
    else:
        author_str = "Unknown Author"
    
    # Build the MLA citation
    mla = f"{author_str}. \"{title}.\" arXiv, {year}."
    
    # Add URL
    if url:
        mla += f" {url}. Accessed {datetime.now().strftime('%d %b. %Y')}."
    
    return mla


def format_chicago(title, authors, year, month, url, doi):
    """Format citation in Chicago style."""
    # Format authors for Chicago
    if authors:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) > 1:
            author_str = f"{authors[0]}, et al."
    else:
        author_str = "Unknown Author"
    
    # Build the Chicago citation
    chicago = f"{author_str}. \"{title}.\" {month} {year}."
    
    # Add DOI or URL
    if doi:
        chicago += f" https://doi.org/{doi}."
    elif url:
        chicago += f" {url}."
    
    return chicago


def format_ieee(title, authors, year, month, url, doi, journal_ref):
    """Format citation in IEEE style."""
    # Format authors for IEEE
    if authors:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} and {authors[1]}"
        else:
            names = [name.split()[-1] for name in authors[:3]]  # Get last names for first 3 authors
            author_str = ", ".join(names) + " et al."
    else:
        author_str = "Unknown Author"
    
    # Build the IEEE citation
    ieee = f"{author_str}, \"{title}\", "
    
    # Add journal reference or arXiv
    if journal_ref:
        ieee += f"{journal_ref}, {year}."
    else:
        ieee += f"arXiv preprint arXiv:{url.split('/')[-1]}, {year}."
    
    # Add DOI if available
    if doi:
        ieee += f" doi: {doi}."
    
    return ieee
