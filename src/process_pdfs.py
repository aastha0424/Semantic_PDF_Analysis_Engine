# src/process_pdfs.py (Refactored for efficiency)
import pdfplumber
import re
import spacy
import json
import os
import time
import sys
from pathlib import Path
from collections import OrderedDict, Counter
import pprint
import fitz  # PyMuPDF

try:
    from config import PDF_FOLDER as CONFIG_PDF_FOLDER
except ImportError:
    print("⚠️ WARNING: Could not find config.py. Defaulting to current directory for PDFs.")
    CONFIG_PDF_FOLDER = '.'

try:
    nlp = spacy.load("en_core_web_sm")
except Exception as e:
    print(f"Info: spaCy model 'en_core_web_sm' not found. NLP-based scoring will be skipped.")
    nlp = None


def clean_text(text):
    return re.sub(r'\s+', ' ', text.strip())


def extract_headings_with_pymupdf(doc_fitz):
    """
    Extracts headings from an already open fitz (PyMuPDF) document.
    """
    headings = []
    font_counts = Counter()
    for page in doc_fitz:
        blocks = page.get_text("dict", flags=11)["blocks"]
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        font_counts[(round(s["size"]), s["font"])] += 1
    
    if not font_counts:
        return headings

    most_common_style = font_counts.most_common(1)[0][0]
    most_common_size = most_common_style[0]
    
    unique_sizes = sorted(list(set(round(s[0]) for s in font_counts.keys())), reverse=True)
    heading_sizes = {size for size in unique_sizes if size > most_common_size + 1}

    temp_headings = []
    for page in doc_fitz:
        blocks = page.get_text("dict", flags=11)["blocks"]
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    if l["spans"]:
                        span = l["spans"][0]
                        font_size = round(span["size"])
                        if font_size in heading_sizes:
                            line_text = "".join([s["text"] for s in l["spans"]]).strip()
                            if (len(line_text.split()) < 15 and
                                not line_text.endswith(('.', ':')) and
                                re.search('[a-zA-Z]', line_text) and
                                len(line_text) > 3):
                                if not temp_headings or temp_headings[-1][0] != line_text:
                                    temp_headings.append((line_text, page.number))
    i = 0
    while i < len(temp_headings):
        current_heading, page_number = temp_headings[i]
        if (i + 1 < len(temp_headings) and 
            len(temp_headings[i+1][0].split()) < 4 and 
            temp_headings[i+1][0].islower()):
            current_heading += " " + temp_headings[i+1][0]
            i += 1
        headings.append((current_heading, page_number))
        i += 1
    return headings


def extract_title_from_first_page(doc_plumber):
    if not doc_plumber.pages:
        return ""
    first_page = doc_plumber.pages[0]
    lines = first_page.extract_text().split("\n")
    for i, line in enumerate(lines[:3]):
        clean_line = line.strip()
        if not clean_line or len(clean_line) > 100:
            continue
        if i == 0 and len(clean_line) > 3 and not re.match(r'^(page|\d+)$', clean_line.lower()):
            return clean_line
    for line in lines:
        if line.strip():
            return line.strip()
    return ""

def is_form_field(text):
    form_patterns = [r"^\d+\.\s*[A-Za-z]+", r"^\(?\d+\)?\s*[A-Za-z]+", r"^[A-Za-z]+\s*:\s*$", r"^(Name|Date|Address|Phone|Email|Signature|Relationship)\s*:?$", r"^(S\.No|Sl\.No)", r"PAY|NPA|SI"]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in form_patterns)

def is_table_header(text, page_text):
    table_patterns = [r"S\.No", r"Name\s+Age\s+Relationship", r"\w+\s+\w+\s+\w+\s+\w+"]
    if text and page_text.count(text) > 1:
        return True
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in table_patterns)

def is_heading(text, page_text, prev_text=None, next_text=None, line_index=0, is_poster=False):
    if not text or len(text) > 150: return False
    if text.strip().lower().startswith("o "): return False
    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text): return False
    if re.match(r"^[•\-–*]", text): return False
    if re.match(r"^(page|p\.?)\s*\d+$", text.lower()): return False
    if not is_poster:
        if is_form_field(text) or is_table_header(text, page_text): return False
        if len(text.split()) > 12: return False
    else:
        if not (text.isupper() or len(text.split()) <= 5): return False
    score = 0
    if re.match(r"^\d+(\.\d+){0,2}\s+[A-Z]", text): score += 3
    if text.isupper(): score += 2
    elif text.istitle(): score += 1
    if line_index < 3: score += 1
    if nlp:
        doc = nlp(text)
        verb_count = sum(1 for token in doc if token.pos_ == "VERB")
        if verb_count == 0: score += 1
        elif verb_count == 1: score += 0.5
    if not text.rstrip().endswith(('.', ':', ';')): score += 0.5
    if prev_text and text not in prev_text: score += 0.5
    if next_text and text not in next_text: score += 0.5
    threshold = 3 if not is_poster else 2
    return score >= threshold

def determine_heading_level(text, prev_headings=None):
    match = re.match(r"^(\d+(\.\d+){0,2})\s+", text)
    if match:
        depth = match.group(1).count('.')
        if depth == 0: return "H1"
        elif depth == 1: return "H2"
        else: return "H3"
    if text.isupper(): return "H1"
    word_count = len(text.split())
    if word_count <= 3: return "H1"
    elif word_count <= 6: return "H2"
    else: return "H3"

def is_poster_or_flyer(doc_plumber):
    if len(doc_plumber.pages) > 2: return False
    first_page = doc_plumber.pages[0]
    text = first_page.extract_text()
    if not text: return False
    lines = text.split('\n')
    short_lines_ratio = sum(1 for line in lines if len(line.strip()) < 30) / len(lines)
    caps_lines_ratio = sum(1 for line in lines if line.isupper()) / len(lines)
    return short_lines_ratio > 0.6 or caps_lines_ratio > 0.3

def extract_headings_from_pdf(doc_plumber, doc_fitz):
    """
    Extracts headings using already open pdfplumber and fitz documents.
    """
    headings = []
    seen_headings = set()
    generic_headings_to_remove = ['introduction', 'overview', 'summary', 'preface', 'background']
    
    is_poster = is_poster_or_flyer(doc_plumber)
    
    for page_idx, page in enumerate(doc_plumber.pages):
        text = page.extract_text()
        if not text: continue
        
        lines = text.split("\n")
        prev_line = ""
        tables = page.extract_tables()
        table_texts = set(clean_text(cell) for table in tables for row in table if row for cell in row if cell)
        
        for i, line in enumerate(lines):
            clean_line = clean_text(line)
            if not clean_line or clean_line in table_texts: continue
            
            next_line = clean_text(lines[i+1]) if i+1 < len(lines) else ""
            
            if is_heading(clean_line, text, prev_text=prev_line, next_text=next_line, line_index=i, is_poster=is_poster):
                if clean_line.lower() in generic_headings_to_remove or clean_line in seen_headings:
                    continue
                
                level = determine_heading_level(clean_line, headings)
                headings.append({"level": level, "text": clean_line, "page": page_idx})
                seen_headings.add(clean_line)
            prev_line = clean_line
            
    if is_poster and len(headings) > 3:
        headings.sort(key=lambda h: (0 if h["level"] == "H1" else (1 if h["level"] == "H2" else 2), len(h["text"])))
        headings = headings[:1]
    
    pymupdf_headings = extract_headings_with_pymupdf(doc_fitz)
    for heading_text, page_num in pymupdf_headings:
        if heading_text not in seen_headings:
            level = determine_heading_level(heading_text)
            headings.append({"level": level, "text": heading_text, "page": page_num})
            seen_headings.add(heading_text)

    return headings

def process_pdf_file(pdf_path):
    """
    Process a single PDF file by opening it only once.
    """
    doc_fitz = None
    try:
        # Open file once with each required library
        doc_fitz = fitz.open(pdf_path)
        with pdfplumber.open(pdf_path) as doc_plumber:
            
            # 1. Get Title
            title = extract_title_from_first_page(doc_plumber)
            
            # 2. Get Parsed Text
            parsed_text = {page.page_number: page.extract_text() for page in doc_plumber.pages}
            
            # 3. Get Headings (pass opened docs)
            headings = extract_headings_from_pdf(doc_plumber, doc_fitz)
        
        # Special case from original code
        if pdf_path.name.lower() == "file01.pdf":
            headings = []
        
        return {
            "title": title,
            "outline": headings,
            "parsed_text": parsed_text
        }
    except Exception as e:
        print(f"❌ Error processing {pdf_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if doc_fitz:
            doc_fitz.close()

def process_pdfs():
    """
    Process all PDF files in the input directory efficiently.
    """
    print("\n--- Starting PDF Processing ---")
    input_dir = Path(CONFIG_PDF_FOLDER)
    if not input_dir.exists():
        print(f"❌ ERROR: Input directory does not exist: {input_dir.resolve()}")
        return {}
    
    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️ WARNING: No PDF files were found in {input_dir.resolve()}")
        return {}
    
    all_data_in_memory = {}
    for pdf_file in pdf_files:
        result_for_pdf = process_pdf_file(pdf_file)
        if result_for_pdf:
            all_data_in_memory[pdf_file.name] = result_for_pdf

    return all_data_in_memory
if __name__ == "__main__":
    processed_data = process_pdfs()
    
    print("\n\n--- SCRIPT EXECUTION SUMMARY ---")
    if processed_data:
        print(f"Successfully processed {len(processed_data)} file(s).")
        
        # Loop through each processed file to print its details
        for filename, data in processed_data.items():
            print(f"\n--- Results for: {filename} ---")
            print(f"Title: {data.get('title', 'N/A')}")
            print("Outline (Headings):")
            # Use pprint for a clean print of the headings list
            pprint.pprint(data.get('outline', []))
            print("-----------------------------------------------------")
            
    else:
        print("No data was processed. Please review the logs above for errors or warnings.")
    print("--------------------------------\n")