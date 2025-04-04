# arXiv Gemini App

A command-line tool for searching arXiv, downloading papers, and using Google's Gemini AI to analyze and extract information from research papers.

## Features

- Search arXiv for papers with customizable sorting and filtering
- Download PDFs of papers
- Ask questions about papers using Google's Gemini AI
- Summarize papers in different styles
- Extract structured data from papers
- Compare multiple papers
- Find related work using intelligent keyword extraction with Gemini and Google Scholar (via Serper API)
- Export citations in various formats (BibTeX, APA, MLA, Chicago, IEEE)

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up API keys:
   - Copy `.env.example` to `.env`
   - Add your Gemini API key (get from https://ai.google.dev/)
   - Add your Serper API key (get from https://serper.dev/) if you want to use the related work feature

## Usage

Run the app in interactive mode:
```
python main.py
```

Or use command-line arguments for non-interactive mode:
```
python main.py --query "your search query" --download 1 --ask 1 "What is the main contribution of this paper?"
```

## Commands

- `q` - Enter a new arXiv search query
- `n` - Fetch the next page of results
- `download [N,M,...]` - Download PDF(s) for result number(s) N,M,... (comma-separated or single number)
- `ask [N] "[Q]"` - Ask Gemini a question about PDF N
- `ask_fig [N] "[Q]"` - Ask Gemini about figures/tables in PDF N
- `sum [N] [style]` - Summarize PDF N using Gemini (styles: simple, technical, key_findings, eli5)
- `ext [N] [type]` - Extract structured data from PDF N (types: methods, conclusion, datasets)
- `compare [N1,N2,...] [type]` - Compare multiple papers using Gemini
- `rel [N]` - Find related work for paper N using Google Scholar (requires Serper API key)
- `cite [N] [format]` - Export citation for paper N in specified format (formats: bibtex, apa, mla, chicago, ieee)
- `set max [N]` - Set max results per page
- `set sort [field] [order]` - Set sort order
- `set model [name]` - Set Gemini model
- `show downloads` - List downloaded/uploaded PDFs
- `show model` - Show current Gemini model
- `help` - Show help message
- `quit` - Exit

## License

MIT
