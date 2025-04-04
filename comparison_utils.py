"""
Comparison utilities for the arXiv Gemini App.
Provides functions to compare multiple papers using Gemini AI.
"""

# Comparison types
COMPARISON_TYPES = {
    "general": "General comparison of the papers, including key similarities and differences.",
    "methods": "Comparison of research methodologies, approaches, and techniques used.",
    "results": "Comparison of key findings, results, and conclusions.",
    "impact": "Comparison of potential impact, applications, and significance in the field."
}

def get_comparison_prompt(comparison_type="general"):
    """
    Get the appropriate prompt for the specified comparison type.

    Args:
        comparison_type (str): The type of comparison to perform.

    Returns:
        str: The prompt to send to Gemini AI.
    """
    if comparison_type not in COMPARISON_TYPES:
        comparison_type = "general"

    base_prompt = """I'm providing you with multiple research papers. IMPORTANT: You must analyze ALL the provided papers and compare them with each other. Make sure to identify each paper by its title and authors in your analysis.

For each paper, first identify its title and authors, then proceed with the comparison. """

    if comparison_type == "general":
        prompt = base_prompt + """Please analyze and compare ALL these papers, focusing on:
1. Key similarities and differences in their approaches
2. How they relate to each other (complementary, contradictory, building upon each other)
3. Main contributions of each paper
4. Strengths and limitations of each approach
5. A brief summary of how these papers collectively advance the field

Format your response with clear headings and bullet points where appropriate. Make sure to reference each paper by title throughout your analysis."""

    elif comparison_type == "methods":
        prompt = base_prompt + """Please analyze and compare the methodologies used in ALL these papers, focusing on:
1. Research approaches and techniques employed in each paper
2. Similarities and differences in their methodological frameworks
3. Experimental designs, datasets, and evaluation metrics
4. Methodological strengths and limitations
5. Innovations in research methods introduced by each paper

Format your response with clear headings and bullet points where appropriate. Make sure to reference each paper by title throughout your analysis."""

    elif comparison_type == "results":
        prompt = base_prompt + """Please analyze and compare the results and findings of ALL these papers, focusing on:
1. Key results and conclusions from each paper
2. Areas of agreement and disagreement in their findings
3. Comparative analysis of the significance of their results
4. Limitations and uncertainties in their conclusions
5. How the results collectively contribute to knowledge in the field

Format your response with clear headings and bullet points where appropriate. Make sure to reference each paper by title throughout your analysis."""

    elif comparison_type == "impact":
        prompt = base_prompt + """Please analyze and compare the potential impact of ALL these papers, focusing on:
1. Practical applications and implications of each paper
2. Potential influence on future research directions
3. Broader impact on the field and related disciplines
4. Comparative assessment of their significance and novelty
5. Long-term relevance and potential for further development

Format your response with clear headings and bullet points where appropriate. Make sure to reference each paper by title throughout your analysis."""

    return prompt
