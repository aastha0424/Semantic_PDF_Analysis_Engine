# src/main.py (Updated to use a single processing step)
import pprint
import os
from pathlib import Path
# Local module imports for the processing pipeline
from config import INPUT_JSON_PATH, OUTPUT_JSON_PATH, PDF_FOLDER
from utils import load_input, generate_output_json
from analyzer import analyze_persona_job
from process_pdfs import process_pdfs # We no longer need parser.py
from ranker import rank_sections


def main():
    """
    Main function to run the entire PDF analysis and ranking pipeline.
    """
    print("--- Starting the Document Analysis Pipeline ---")

    # Step 1: Load input data (persona, job, etc.) from the input JSON file
    print(f"Loading input data from: {INPUT_JSON_PATH}")
    try:
        input_data = load_input(INPUT_JSON_PATH)
        persona = input_data["persona"]
        task = input_data["job_to_be_done"]
        challenge_info = input_data["challenge_info"]
        print("✅ Input data loaded successfully.")
    except FileNotFoundError:
        print(f"❌ ERROR: Input file not found at {INPUT_JSON_PATH}. Please ensure the file exists.")
        return
    except KeyError as e:
        print(f"❌ ERROR: Missing expected key {e} in {INPUT_JSON_PATH}.")
        return


    # Step 2: Process all PDFs to extract titles, outlines, and full text in a SINGLE PASS.
    print("\n--- Stage 1: Processing PDFs (Single Pass) ---")
    all_processed_data = process_pdfs() # This now contains titles, outlines, and parsed_text
    if not all_processed_data:
        print("❌ ERROR: No PDF data was processed. Please check your PDF folder and configuration.")
        return
    print(f"✅ Successfully processed {len(all_processed_data)} documents in a single pass.")


    # Step 3: Prepare the exact inputs for the analyzer from the processed data.
    # The separate call to parse_documents is now removed.
    print("\n--- Stage 2: Preparing Data for Analysis ---")

    # Create the 'parsed_docs' dictionary in the format the analyzer expects.
    # This uses the 'parsed_text' key from our single-pass result.
    parsed_docs = {filename: data['parsed_text'] for filename, data in all_processed_data.items() if 'parsed_text' in data}

    # The 'all_outlines_data' is the same rich dictionary, as it contains the 'outline' and 'title' for each file.
    all_outlines_data = all_processed_data
    print("✅ Data prepared for analyzer.")


    # Step 4: Analyze the documents to find sections relevant to the persona and task.
    print("\n--- Stage 3: Analyzing Sections for Relevance ---")
    matched_sections = analyze_persona_job(
        parsed_docs,
        persona,
        task,
        challenge_info,
        all_outlines_data, # Pass the full structure
        max_results=10
    )
    print(f"✅ Analysis complete. Found {len(matched_sections)} potentially relevant sections.")


    # Step 5: Rank the matched sections and generate the final output JSON.
    print("\n--- Stage 4: Ranking Sections and Generating Output ---")
    ranked_sections, subsections = rank_sections(matched_sections, persona, task)
    generate_output_json(input_data, ranked_sections, subsections, OUTPUT_JSON_PATH)
    print(f"✅ Final output generated at: {OUTPUT_JSON_PATH}")
    print("\n--- Document Analysis Pipeline Finished ---")


if __name__ == "__main__":
    main()