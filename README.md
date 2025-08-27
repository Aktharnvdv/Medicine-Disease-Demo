# Medicine-Disease-Demo


Project Documentation: Medicine Analyzer API
This document outlines the functionality and technical details of the Medicine Analyzer API, a Flask-based web application that uses the Google Gemini-1.5-flash-latest model to analyze PDF documents. The application identifies medicines listed in a PDF and classifies them as relevant or irrelevant for treating a specified disease.

Table of Contents
Overview

Features

How It Works

Code Breakdown

Configuration

Helper Functions

API Routes

Main Execution

Setup and Usage

API Endpoint Details

POST /api/analyze

1. Overview
The Medicine Analyzer API is a Python web service built with Flask. Its primary purpose is to automate the process of reviewing lists of medications from a PDF file. It takes a disease name and a PDF as input, extracts the text, sends it in chunks to the Google Gemini API, and processes the AI-generated classifications. The final output is a structured JSON response detailing which medicines are relevant or irrelevant to the given disease, along with explanations.

Core Technologies:

Backend: Flask

AI Model: Google Gemini 1.5 Flash

PDF Processing: pdfplumber

HTTP Requests: requests

Environment Management: python-dotenv

2. Features
Web Interface: Simple Flask server to handle API requests.

PDF Text Extraction: Reliably extracts both plain text and structured table data from PDF files.

AI-Powered Classification: Leverages the Google Gemini model to perform nuanced classification of medicines based on a clinical context.

Large Document Handling: Splits long documents into smaller chunks to process them efficiently without exceeding API limits.

Robust JSON Parsing: Includes multiple fallbacks to correctly parse JSON from the model's response, even if it's slightly malformed or embedded in markdown.

Rate Limiting: Implements a delay between API calls to prevent hitting rate limits.

Detailed API Response: Returns aggregated results, per-chunk processing details, and usage statistics (token counts, time elapsed).

3. How It Works
The application follows a clear, multi-step process:

User Request: A user sends a POST request to the /api/analyze endpoint with a disease name and a pdf file.

Input Validation: The server checks if the disease and PDF file are present.

PDF Parsing: The pdfplumber library reads the uploaded PDF in memory and extracts all text and table content, page by page. Tables are converted into a Tab-Separated Value (TSV) format.

Text Chunking: The extracted text is split into lines, and these lines are grouped into smaller "chunks" (defaulting to 50 lines each). This ensures each API request is a manageable size.

Iterative API Calls: The application loops through each chunk:
a. A detailed prompt is constructed, instructing the Gemini model to act as a clinical pharmacist and classify medicines from the chunk as "relevant" or "irrelevant" for the specified disease. The prompt demands a strict JSON output format.
b. The call_gemini function sends the request to the Google Generative Language API.
c. The response is received and parsed. The system first tries to extract a clean JSON object. If that fails, it uses a more resilient parser (safe_parse) that can handle messy or non-standard model outputs.

Data Aggregation: The results from each chunk are processed. Unique medicines are added to aggregated lists for relevant and irrelevant classifications to avoid duplicates.

Final Response: Once all chunks are processed, the server compiles a final JSON response containing the sorted, unique lists of relevant and irrelevant medicines, detailed results for each chunk, and a summary of the total API calls and token usage.

4. Code Breakdown
The script is organized into logical sections for clarity.

1. Configuration
This section initializes settings and constants for the application.

load_dotenv(): Loads environment variables from a .env file.

GEMINI_API_KEY: Fetches the API key from the environment. The script will raise an error if it's not set.

MODEL & API_URL: Defines the specific Gemini model and constructs the full API endpoint URL.

RATE_DELAY, CHUNK_LINES, REQUEST_TIMEOUT: Constants to control the rate of API calls, the size of text chunks, and the HTTP request timeout.

app = Flask(...): Initializes the Flask application and sets a maximum content length for uploads (20 MB).

2. Helper Functions
This section contains the core logic for PDF extraction, API communication, and data parsing.

extract_text_from_pdf(data: bytes) -> str:

Takes the raw bytes of a PDF file.

Uses pdfplumber to open the PDF.

Iterates through each page, extracting body text and tables.

Formats tables with a header and tab-separated rows.

Returns all content as a single newline-separated string.

chunk_list(lines, n):

A simple generator that takes a list of lines and yields chunks of n lines, joined by newlines.

build_prompt(disease: str, block: str) -> str:

Constructs the precise prompt sent to the Gemini API.

It defines the persona ("experienced clinical pharmacist"), the task (classify medicines), and the strict JSON output format required.

It dynamically inserts the disease and the text block (chunk) to be analyzed.

_strip_fence(text: str) -> str:

A utility function to remove Markdown code fences (e.g., ` json ...

call_gemini(prompt: str) -> Dict:

Sends the prompt to the Gemini API via a POST request.

Handles the JSON payload, headers, and timeout.

Parses the response to extract the generated text, token usage, and status. It attempts to combine JSON from multiple parts in the model's response if they exist.

Returns a dictionary with status (ok), the parsed json, usage stats, and elapsed time.

_normalize_list(lst):

A data sanitization function. It ensures that a list of medicines (e.g., relevant) contains properly formatted dictionaries ({"name": "...", "explanation": "..."}). It can handle cases where the model returns a simple list of strings instead of a list of objects.

safe_parse(reply: str) -> dict:

A robust JSON parser designed to handle imperfect LLM output.

Attempt 1: It uses regex to find the first {...} block, cleans it of trailing commas (a common JSON error), and tries to parse it.

Attempt 2 (Fallback): If the first attempt fails, it uses regex to find sections marked "Relevant" and "Irrelevant" and extracts their contents as bulleted lists.

It always returns a dictionary with relevant and irrelevant keys, even if they are empty lists.

3. API Routes
This section defines the web endpoints.

@app.route("/"):

The root URL.

Renders and serves the index.html file, which is the main user interface.

@app.route("/api/analyze", methods=["POST"]):

The main API endpoint for processing PDFs.

It orchestrates the entire workflow described in the How It Works section.

It handles form validation, calls the helper functions, aggregates results, and returns the final JSON response or an error message.

Includes a try...except block to catch unexpected server errors and return a 500 status code.

4. Main Execution
if __name__ == "__main__"::

The standard Python entry point.

Runs the Flask development server on 0.0.0.0:5000 with debug mode enabled.

5. Setup and Usage
To run this application locally, follow these steps:

Prerequisites: Ensure you have Python 3 and pip installed.

Dependencies: Install the required Python libraries. Create a requirements.txt file with the following content:

text
flask
python-dotenv
requests
pdfplumber
Then, run:

bash
pip install -r requirements.txt
Environment Variables: Create a file named .env in the same directory as the script. Add your Google Gemini API key to it:

text
GEMINI_API_KEY="YOUR_API_KEY_HERE"
Run the Server: Execute the script from your terminal:

bash
python your_script_name.py
The server will start and be accessible at http://0.0.0.0:5000 or http://localhost:5000.

6. API Endpoint Details
POST /api/analyze
This endpoint analyzes a PDF file to classify medicines based on a given disease.

Method: POST

Content-Type: multipart/form-data

Form Data:

disease (string): Required. The name of the disease to use for classification (e.g., "Hypertension").

pdf (file): Required. The PDF file to be analyzed.

Success Response (200 OK)
The API returns a JSON object with the final aggregated results and detailed metadata.

        json
        {
        "relevant": [
            {"name": "Lisinopril", "explanation": "An ACE inhibitor commonly used to lower blood pressure in treating hypertension."}
        ],
        "irrelevant": [
            {"name": "Ibuprofen", "explanation": "A nonsteroidal anti-inflammatory drug (NSAID) that can potentially increase blood pressure."}
        ],
        "results": [
            {
            "idx": 1,
            "elapsed": 1.85,
            "usage": {"in": 150, "out": 45},
            "relevant": [...],
            "irrelevant": [...],
            "status": 200
            }
        ],
        "summary": {
            "calls": 1,
            "tokens_in": 150,
            "tokens_out": 45
        }
        }
Error Responses:

400 Bad Request: Returned if disease or pdf is missing from the form, or if the file is empty.

500 Internal Server Error: Returned for any unhandled exceptions on the server side. The JSON body will contain an error key with the exception message.