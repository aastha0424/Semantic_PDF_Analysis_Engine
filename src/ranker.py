from collections import defaultdict
from transformers import pipeline
import logging
import os
import re

# Setup logging
logging.basicConfig(level=logging.INFO)

# Removed 'show_progress_bar' to prevent errors
model_name = os.getenv("SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-6-6")
summarizer = pipeline("summarization", model=model_name)


def clean_final_text(text: str) -> str:
    """
    A comprehensive cleaning function to be run before finalizing output.
    - Fixes various bullet point styles.
    - Strips out non-standard symbols (like °).
    - Preserves list structure for better summarization.
    """
    if not isinstance(text, str):
        return ""

    # Fix bullet points
    text = re.sub(r'[\uf0b7\u2022]', '*', text)
    text = re.sub(r'^\s*o\s+', '* ', text, flags=re.MULTILINE)

    # Remove unwanted symbols, keeping letters, numbers, and basic punctuation
    text = re.sub(r'[^\w\s.,!?"\'()-]', '', text, flags=re.UNICODE)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


# In src/ranker.py

def rank_sections(matches, persona, task, max_total=6, max_per_document=2):
    sorted_matches = sorted(matches, key=lambda x: x['score'], reverse=True)
    doc_count = defaultdict(int)
    output_sections = []
    subsections_to_refine = [] # Collect data for refinement
    rank = 1

    for section in sorted_matches:
        doc = section['document']
        
        if not section['text'].strip():
            logging.info(f"Skipping section '{section['section_title']}' in {doc} due to empty associated text.")
            continue

        if doc_count[doc] >= max_per_document:
            continue

        output_sections.append({
            "document": doc,
            "section_title": section['section_title'],
            "importance_rank": rank,
            "page_number": section['page_number']
        })

        # Collect the necessary information for later processing
        subsections_to_refine.append({
            "document": doc,
            "text": section['text'],
            "page_number": section['page_number']
        })

        doc_count[doc] += 1
        rank += 1

        if len(output_sections) >= max_total:
            break
            
    # Batch refine the subsections
    refined_subsections = refine_subsection_batch(subsections_to_refine)

    return output_sections, refined_subsections


def refine_subsection_batch(subsections_data):
    """
    Summarizes a batch of subsection texts.
    """
    if not subsections_data:
        return []

    # Clean all texts first
    for item in subsections_data:
        item['cleaned_text'] = clean_final_text(item['text'])

    # Separate short texts from those needing summarization
    texts_to_summarize = [
        item['cleaned_text'] for item in subsections_data if len(item['cleaned_text'].split()) >= 40
    ]
    
    summaries = []
    if texts_to_summarize:
        try:
            # Summarize all long texts in one batch
            summaries = summarizer(
                texts_to_summarize, max_length=300, min_length=70, do_sample=False, truncation=True, batch_size=4
            )
        except Exception as e:
            logging.warning(f"Batch summarization failed. Error: {e}")
            # Fallback to returning the cleaned text for all items if batch fails
            summaries = [{'summary_text': text} for text in texts_to_summarize]

    summary_iter = iter(summaries)
    final_subsections = []
    for item in subsections_data:
        refined_text = ""
        if len(item['cleaned_text'].split()) < 40:
            refined_text = item['cleaned_text'] # Use cleaned text if it was too short
        else:
            try:
                # Pop the next available summary
                refined_text = next(summary_iter)['summary_text'].strip()
            except StopIteration:
                 # Fallback in case of an issue
                refined_text = item['cleaned_text']

        final_subsections.append({
            "document": item['document'],
            "refined_text": refined_text,
            "page_number": item['page_number']
        })
        
    return final_subsections


# You can remove the old `refine_subsection` function as it's replaced by the batch version.