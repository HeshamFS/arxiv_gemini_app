import google.generativeai as genai
from google.genai.types import Tool, GoogleSearch
import os
import time
import sys # Import sys for traceback printing if needed
import json # For pretty printing JSON
import requests
import traceback # For printing stack traces

# Import comparison utilities
import comparison_utils

# Function to generate text content with Gemini
async def generate_content(prompt, model_name="gemini-2.5-pro-exp-03-25"):
    """
    Generates text content using Gemini.

    Args:
        prompt (str): The prompt to send to Gemini.
        model_name (str): The Gemini model to use.

    Returns:
        object: The response object from Gemini, or None if an error occurs.
    """
    try:
        model = genai.GenerativeModel(model_name)
        response = await model.generate_content_async(prompt)
        return response
    except Exception as e:
        print(f"[!] Error generating content with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return None

# Configure the Gemini client (ideally call configure() from main.py)
# genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Using simple dictionaries which the SDK often accepts for schemas
# Based loosely on OpenAPI subset described in Gemini docs
EXTRACTION_SCHEMAS = {
    "methods": {
        "type": "object",
        "properties": {
            "methodologies": {
                "type": "array",
                "description": "List of key methodologies, techniques, or approaches used in the paper.",
                "items": {"type": "string"}
            }
        },
        "required": ["methodologies"]
    },
    "conclusion": {
        "type": "object",
        "properties": {
            "main_conclusion": {
                "type": "string",
                "description": "The main conclusion or takeaway message of the paper."
            },
            "future_work": {
                "type": "array",
                "description": "Suggestions for future work mentioned in the paper.",
                "items": {"type": "string"}
            }
        },
         "required": ["main_conclusion"] # Future work might not always be present
    },
    "datasets": {
         "type": "object",
         "properties": {
             "datasets_used": {
                 "type": "array",
                 "description": "List of specific datasets mentioned as being used or analyzed in the paper.",
                 "items": {
                     "type": "object",
                     "properties": {
                        "name": {"type": "string", "description": "Name of the dataset"},
                        "source": {"type": "string", "description": "Source or reference for the dataset (if mentioned)"}
                     },
                     "required": ["name"]
                 }
             }
         },
         "required": ["datasets_used"]
    },
    # Add more schemas here as needed (e.g., 'key_results', 'contributions')
}

# --- Placeholder Functions ---

def configure_gemini(api_key):
    """Configures the Gemini client."""
    try:
        genai.configure(api_key=api_key)
        print("[*] Gemini API configured successfully.")
        # Optionally check if the API key is valid by making a simple call
        # You can try listing models to verify connection, but handle potential errors
        try:
            models = genai.list_models()
            print("[*] Gemini connection verified (able to list models).")
        except Exception as conn_err:
            print(f"[!] Warning: Could not verify Gemini connection by listing models: {conn_err}")
            print("    Proceeding, but API calls might fail later.")
    except Exception as e:
        print(f"[!] Error configuring Gemini API: {e}")
        print("    Please ensure your GEMINI_API_KEY is set correctly.")
        # Depending on severity, you might want to exit or disable Gemini features
        return False
    return True

async def upload_pdf_to_gemini(filepath, display_name=None):
    """
    Uploads a PDF file to the Gemini File API.

    Args:
        filepath (str): The local path to the PDF file.
        display_name (str, optional): A display name for the file in the API.
                                     Defaults to the base filename.

    Returns:
        genai.File object from Gemini API with ACTIVE state, or None if upload/processing fails.
    """
    print(f"[*] Uploading '{os.path.basename(filepath)}' to Gemini File API...")
    if display_name is None:
        display_name = os.path.basename(filepath)

    uploaded_file = None # Initialize to None
    refreshed_file = None # Initialize to None

    try:
        # The actual File API upload is synchronous in the Python SDK v0.5.x
        uploaded_file = genai.upload_file(path=filepath, display_name=display_name)
        print(f"[+] File uploaded initially. Name: {uploaded_file.name}, State: {uploaded_file.state.name}, URI: {uploaded_file.uri}")

        # *** FIX: Initialize refreshed_file with the initial upload result ***
        refreshed_file = uploaded_file

        # IMPORTANT: Wait for processing
        print(f"[*] Waiting for Gemini to process file: {uploaded_file.name}...")
        file_state = uploaded_file.state.name

        # Poll while the state is PROCESSING
        while file_state == "PROCESSING":
            print(f"    Current state: {file_state}. Waiting 5 seconds...")
            time.sleep(5)
            # Fetch the latest state using get_file
            # genai.get_file is also synchronous
            refreshed_file = genai.get_file(name=uploaded_file.name)
            file_state = refreshed_file.state.name
            print(f"    Refreshed state: {file_state}") # Add more detailed logging

        # After the loop, check the final state
        if file_state == "ACTIVE":
            print(f"[+] File '{uploaded_file.name}' is ACTIVE and ready.")
            # refreshed_file already holds the correct object (either initial or last fetched)
            return refreshed_file
        else:
            print(f"[!] Error: File processing failed or ended in unexpected state: {file_state}")
            # Consider deleting the failed file if it exists and you have the name
            if uploaded_file:
                 try:
                     print(f"[*] Attempting to delete non-ACTIVE file: {uploaded_file.name}")
                     genai.delete_file(name=uploaded_file.name)
                     print(f"[+] Deleted non-ACTIVE file: {uploaded_file.name}")
                 except Exception as delete_err:
                     print(f"[!] Warning: Could not delete non-ACTIVE file {uploaded_file.name}: {delete_err}")
            return None

    except Exception as e:
        print(f"[!] Error uploading or processing file with Gemini API: {e}")
        import traceback
        traceback.print_exc()
         # Clean up potentially failed upload if we have a name
        if uploaded_file and uploaded_file.name:
             try:
                 print(f"[*] Attempting to delete file due to error: {uploaded_file.name}")
                 genai.delete_file(name=uploaded_file.name)
                 print(f"[+] Deleted file due to error: {uploaded_file.name}")
             except Exception as delete_err:
                 print(f"[!] Warning: Could not delete file {uploaded_file.name} after error: {delete_err}")
        return None


async def ask_question_about_pdf(file_object, question, model_name="gemini-2.5-pro-exp-03-25"):
    """
    Asks a question about a previously uploaded PDF using Gemini.

    Args:
        file_object (genai.File): The ACTIVE File object returned by upload_pdf_to_gemini.
        question (str): The question to ask about the PDF content.
        model_name (str): The Gemini model to use (should support File API).

    Returns:
        str: The text response from Gemini, or None if an error occurs.
    """
    if not file_object or not file_object.uri or not file_object.mime_type:
         print("[!] Error: Invalid file object provided for asking question.")
         return None

    print(f"[*] Asking Gemini ('{model_name}') about PDF ({file_object.name} / {file_object.uri}): '{question}'")
    model = genai.GenerativeModel(model_name)

    try:
        # Create the prompt using the File object directly
        # The SDK handles creating the necessary FileDataPart implicitly
        prompt_parts = [
            question,
            file_object # Pass the File object directly
        ]

        # Generate content
        response = await model.generate_content_async(prompt_parts) # Use async version

        print("[+] Gemini responded.")
        # Add safety checks for response structure if needed
        if hasattr(response, 'text'):
            return response.text
        else:
             print("[!] Gemini response structure unexpected. Full response:", response)
             # Attempt to find text in candidates if available
             try:
                 return response.candidates[0].content.parts[0].text
             except (AttributeError, IndexError):
                 print("[!] Could not extract text from Gemini response.")
                 return None


    except Exception as e:
        print(f"[!] Error generating content with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- Example Usage (for testing this module directly) ---
async def _test():
    # Requires GEMINI_API_KEY environment variable
    if "GEMINI_API_KEY" not in os.environ:
        print("Please set the GEMINI_API_KEY environment variable.")
        return

    if not configure_gemini(os.environ["GEMINI_API_KEY"]):
         return

    # Create a dummy PDF file for testing
    dummy_pdf_path = "dummy_test.pdf"
    try:
        # Basic PDF structure (replace with actual PDF library if needed for complex tests)
        with open(dummy_pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n")
            f.write(b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")
            f.write(b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n")
            f.write(b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Resources<<>>/Contents 4 0 R>>endobj\n")
            f.write(b"4 0 obj<</Length 47>>stream\nBT /F1 12 Tf 72 720 Td (Hello PDF World from Gemini Test!) Tj ET\nendstream\nendobj\n")
            f.write(b"xref\n0 5\n0000000000 65535 f\n0000000010 00000 n\n0000000058 00000 n\n0000000116 00000 n\n0000000219 00000 n\ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n306\n%%EOF")
        print(f"Created dummy PDF: {dummy_pdf_path}")

        uploaded_file_obj = await upload_pdf_to_gemini(dummy_pdf_path)

        # Pass the file *object* to the ask function
        if uploaded_file_obj and uploaded_file_obj.state.name == "ACTIVE":
            print("\n--- Asking Question ---")
            question = "What text message is inside this document?"
            answer = await ask_question_about_pdf(
                file_object=uploaded_file_obj, # Pass the object
                question=question
            )
            if answer:
                print(f"\nQ: {question}")
                print(f"A: {answer}")
            else:
                 print("[!] Did not receive an answer from Gemini.")

            # --- Clean up ---
            print(f"\n[*] Deleting uploaded file: {uploaded_file_obj.name}")
            try:
                 genai.delete_file(name=uploaded_file_obj.name)
                 print("[+] File deleted.")
            except Exception as delete_err:
                 print(f"[!] Warning: Failed to delete file {uploaded_file_obj.name}: {delete_err}")
        else:
            print("[!] Skipping question as file upload/processing failed.")

    finally:
        if os.path.exists(dummy_pdf_path):
             os.remove(dummy_pdf_path)
             print(f"Removed dummy PDF: {dummy_pdf_path}")

async def summarize_or_explain_pdf(file_object, request_type="summarize", style="default", model_name="gemini-2.5-pro-exp-03-25"):
    """
    Generates a summary or explanation for a PDF using Gemini.

    Args:
        file_object (genai.File): The ACTIVE File object from upload_pdf_to_gemini.
        request_type (str): 'summarize' or 'explain'.
        style (str): Optional style hint (e.g., 'simple', 'technical', 'key_findings', 'eli5').
        model_name (str): The Gemini model to use.

    Returns:
        str: The text response from Gemini, or None if an error occurs.
    """
    if not file_object or not file_object.uri or not file_object.mime_type:
         print("[!] Error: Invalid file object provided for summarizing/explaining.")
         return None

    # Construct the prompt based on request type and style
    if request_type == "explain":
        prompt = f"Explain the main concepts and findings of the document attached."
        if style != "default" and style:
            prompt += f" Use a {style} style."
    else: # Default to summarize
        if style == "key_findings":
             prompt = "Summarize the key findings and results presented in the attached document."
        elif style == "technical":
             prompt = "Provide a technical summary of the attached document, focusing on methodology and results for a researcher in the field."
        elif style == "simple" or style == "eli5":
             prompt = "Provide a simple, easy-to-understand summary of the main points of the attached document. Explain it like I'm 5 years old."
        else: # Default summary
            prompt = "Provide a concise summary of the attached document."

    print(f"[*] Asking Gemini ('{model_name}') to {request_type} PDF ({file_object.name}) (Style: {style})")
    model = genai.GenerativeModel(model_name)
    # Prepare system instruction if needed (can refine prompt engineering)
    system_instruction = None # Example: "Focus on the practical implications."

    try:
        prompt_parts = [
            prompt,
            file_object # Pass the File object directly
        ]

        generation_config = {} # Add temperature etc. if needed
        safety_settings = None # Use default safety settings

        response = await model.generate_content_async(
            prompt_parts,
            generation_config=generation_config,
            safety_settings=safety_settings,
            # system_instruction=system_instruction # Add if using system instructions
            )

        print("[+] Gemini responded.")
        if hasattr(response, 'text'):
            return response.text
        else:
             print("[!] Gemini response structure unexpected. Full response:", response)
             try: # Attempt fallback extraction
                 return response.candidates[0].content.parts[0].text
             except (AttributeError, IndexError):
                 print("[!] Could not extract text from Gemini response.")
                 return None

    except Exception as e:
        print(f"[!] Error generating summary/explanation with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return None


async def extract_structured_data(file_object, schema_key, model_name="gemini-2.5-pro-exp-03-25"):
    """
    Extracts structured data (JSON) from a PDF using a predefined schema.

    Args:
        file_object (genai.File): The ACTIVE File object from upload_pdf_to_gemini.
        schema_key (str): The key corresponding to a schema in EXTRACTION_SCHEMAS.
        model_name (str): The Gemini model to use.

    Returns:
        str: JSON string response from Gemini, or None if an error occurs.
    """
    if not file_object or not file_object.uri or not file_object.mime_type:
         print("[!] Error: Invalid file object provided for extraction.")
         return None

    if schema_key not in EXTRACTION_SCHEMAS:
        print(f"[!] Error: Unknown extraction schema key: '{schema_key}'")
        print(f"    Available keys: {', '.join(EXTRACTION_SCHEMAS.keys())}")
        return None

    schema = EXTRACTION_SCHEMAS[schema_key]
    # Construct a prompt that asks for the specific type of information
    prompt = f"Extract the following information from the attached document according to the provided JSON schema: {schema_key}."
    # Alternative prompt: "Analyze the attached document and extract information about its {schema_key}. Format the output as JSON using the provided schema."

    print(f"[*] Asking Gemini ('{model_name}') to extract '{schema_key}' from PDF ({file_object.name}) as JSON")
    # Use a model that explicitly supports JSON mode well, like Flash or Pro
    model = genai.GenerativeModel(model_name)

    try:
        prompt_parts = [
            prompt,
            file_object # Pass the File object directly
        ]

        # Configure for JSON output
        generation_config = genai.types.GenerationConfig(
             response_mime_type="application/json",
             response_schema=schema # Pass the schema dictionary/object
        )

        safety_settings = None # Use default safety settings

        response = await model.generate_content_async(
            prompt_parts,
            generation_config=generation_config,
            safety_settings=safety_settings,
            )

        print("[+] Gemini responded (expecting JSON).")

        # The response.text should contain the JSON string
        if hasattr(response, 'text'):
            # Optional: Validate if it's valid JSON before returning
            try:
                json.loads(response.text) # Try parsing
                return response.text # Return the raw JSON string
            except json.JSONDecodeError as json_err:
                 print(f"[!] Gemini response was not valid JSON: {json_err}")
                 print("    Raw Response Text:", response.text)
                 return None # Indicate failure
            except Exception as e:
                print(f"[!] Unexpected error processing Gemini JSON response: {e}")
                return None

        else: # Fallback check in candidates if needed
             print("[!] Gemini response structure unexpected (no .text). Full response:", response)
             try:
                 json_text = response.candidates[0].content.parts[0].text
                 json.loads(json_text) # Validate
                 return json_text
             except (AttributeError, IndexError, json.JSONDecodeError) as fallback_err:
                 print(f"[!] Could not extract or validate JSON from Gemini response fallback: {fallback_err}")
                 return None

    except Exception as e:
        # Specific check for errors related to JSON mode / schema incompatibility
        if "response_schema" in str(e) or "mime_type" in str(e):
             print(f"[!] Error likely related to JSON mode/schema configuration with Gemini: {e}")
        else:
            print(f"[!] Error generating structured data with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- FUNCTION for Serper Google Scholar ---
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
        print(f"[DEBUG] Sending request to {search_url}")
        response = requests.post(search_url, headers=headers, data=payload, timeout=20)
        print(f"[DEBUG] Response status code: {response.status_code}")

        # Print raw response for debugging
        print(f"[DEBUG] Raw response preview: {response.text[:200]}...")

        response.raise_for_status()
        search_results = response.json()
        print(f"[DEBUG] Response JSON keys: {list(search_results.keys())}")

        # Extract the relevant 'organic' results list
        organic_results = search_results.get('organic', [])
        print(f"[DEBUG] Found {len(organic_results)} organic results")

        # If no results from Scholar API, try fallback
        if not organic_results:
            print("[*] No results from Scholar API, trying regular search...")
            print(f"[DEBUG] Sending request to {fallback_search_url}")
            response = requests.post(fallback_search_url, headers=headers, data=fallback_payload, timeout=20)
            print(f"[DEBUG] Fallback response status code: {response.status_code}")
            response.raise_for_status()
            search_results = response.json()
            print(f"[DEBUG] Fallback response JSON keys: {list(search_results.keys())}")
            organic_results = search_results.get('organic', [])
            print(f"[DEBUG] Found {len(organic_results)} organic results from fallback")

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
        traceback.print_exc()
        return None

async def compare_papers(file_objects, comparison_type="general", model_name="gemini-2.5-pro-exp-03-25"):
    """
    Compares multiple papers using Gemini AI.

    Args:
        file_objects (list): List of ACTIVE File objects returned by upload_pdf_to_gemini.
        comparison_type (str): Type of comparison to perform (general, methods, results, impact).
        model_name (str): The Gemini model to use (should support File API).

    Returns:
        str: The comparison analysis from Gemini, or None if an error occurs.
    """
    if not file_objects or len(file_objects) < 2:
        print("[!] Error: At least two valid file objects are required for comparison.")
        return None

    # Check that all file objects are valid
    for i, file_obj in enumerate(file_objects):
        if not file_obj or not file_obj.uri or not file_obj.mime_type:
            print(f"[!] Error: Invalid file object at index {i}.")
            return None

    # Get the appropriate prompt for the comparison type
    prompt = comparison_utils.get_comparison_prompt(comparison_type)

    print(f"[*] Asking Gemini ('{model_name}') to compare {len(file_objects)} papers (Type: {comparison_type})")
    model = genai.GenerativeModel(model_name)

    try:
        # Create the prompt parts with all file objects
        prompt_parts = [prompt]

        # Add all file objects to the prompt parts
        for file_obj in file_objects:
            prompt_parts.append(file_obj)

        # Generate content
        response = await model.generate_content_async(prompt_parts)

        print("[+] Gemini responded with comparison analysis.")
        if hasattr(response, 'text'):
            return response.text
        else:
            print("[!] Gemini response structure unexpected. Full response:", response)
            # Attempt to find text in candidates if available
            try:
                return response.candidates[0].content.parts[0].text
            except (AttributeError, IndexError):
                print("[!] Could not extract text from Gemini response.")
                return None

    except Exception as e:
        print(f"[!] Error comparing papers with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    import asyncio
    # To run the test: python gemini_client.py
    # Make sure google-generativeai is installed and GEMINI_API_KEY is set
    print("--- Running gemini_client.py test ---")
    # Ensure compatibility if running on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_test())
    print("--- Test finished ---")