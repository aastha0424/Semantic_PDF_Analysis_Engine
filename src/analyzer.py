# src/analyzer.py

from sentence_transformers import SentenceTransformer, util
from keybert import KeyBERT
import re
from collections import defaultdict
import os
from transformers import pipeline
from pathlib import Path
import spacy
from spacy.tokenizer import Tokenizer

# --- Model Loading ---
# Load SentenceTransformer and KeyBERT models once for efficiency
model = SentenceTransformer('all-MiniLM-L6-v2')
kw_model = KeyBERT(model)

# --- Custom Tokenizer for spaCy to handle hyphens ---
def create_custom_tokenizer(nlp):
    # Create a custom tokenizer that doesn't split on hyphens
    infix_re = re.compile(r'''[.\,\?\!\:\;\...\‘\’\`\“\”\"\'~]''')
    return Tokenizer(nlp.vocab, infix_finditer=infix_re.finditer)

# Load spaCy for linguistic processing
try:
    nlp = spacy.load("en_core_web_sm")
    # Apply the custom tokenizer
    nlp.tokenizer = create_custom_tokenizer(nlp)
except OSError:
    print("Downloading spaCy model 'en_core_web_sm'...")
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")
    nlp.tokenizer = create_custom_tokenizer(nlp)

# # Load title rewriter if available
# try:
#     title_rewriter = pipeline("text2text-generation", model="google/flan-t5-small")
# except:
#     title_rewriter = None  # Skip if not available


# --- Keyword Generation Functions ---

def extract_dynamic_keywords(persona, task, challenge_info, top_n=20):
    """
    (Original Function) Extracts, ranks, and filters task-specific KEYPHRASES.
    """
    persona_role = persona['role']
    task_description = task['task']
    description = challenge_info.get('description', '')
    test_case_name = challenge_info.get('test_case_name', '')
    combined_query_text = (
        f"{persona_role} needs to: {task_description}. "
        f"Challenge description: {description}. "
        f"Test case: {test_case_name}."
    )
    top_n_keybert_initial = top_n
    min_similarity_threshold = 0.2
    initial_keybert_phrases = kw_model.extract_keywords(
        combined_query_text,
        keyphrase_ngram_range=(1, 3),
        stop_words='english',
        top_n=top_n_keybert_initial
    )
    initial_keywords_set = set(kw[0].lower() for kw in initial_keybert_phrases)
    query_embedding = model.encode(combined_query_text, convert_to_tensor=True, show_progress_bar=False)
    ranked_keywords_with_scores = []
    if initial_keywords_set:
        keyword_texts = list(initial_keywords_set)
        keyword_embeddings = model.encode(keyword_texts, convert_to_tensor=True, show_progress_bar=False)
        similarities = util.cos_sim(query_embedding, keyword_embeddings)[0]
        for i, kw_text in enumerate(keyword_texts):
            score = similarities[i].item()
            ranked_keywords_with_scores.append((kw_text, score))
        ranked_keywords_with_scores.sort(key=lambda x: x[1], reverse=True)
    final_ranked_filtered_keywords = []
    for kw, score in ranked_keywords_with_scores:
        if score >= min_similarity_threshold:
            final_ranked_filtered_keywords.append(kw)
            if len(final_ranked_filtered_keywords) >= 10:
                break
    return set(final_ranked_filtered_keywords)

def extract_keywords_simple(task_description):
    """
    (New Function) Extracts important SINGLE WORDS (nouns, verbs, adjectives) using spaCy.
    """
    # Process the text with spaCy
    doc = nlp(task_description.lower())
    
    keywords = []
    for token in doc:
        # Check if the token is a noun, proper noun, adjective, or verb, and not punctuation
        if token.pos_ in ['NOUN', 'PROPN', 'ADJ', 'VERB'] and not token.is_punct:
            keywords.append(token.text)
            
    return set(keywords)


# --- Scoring and Utility Functions ---

def boost_from_title(title, phrase_keywords, simple_keywords):
    """
    (Updated) Gives a boost if any keyword is in the title, with a higher boost for simple keywords.
    """
    title_words = set(title.lower().split())
    boost = 0.0
    # Higher boost for direct keywords from the task
    if not simple_keywords.isdisjoint(title_words):
        boost += 0.1
    # Smaller boost for contextual phrase keywords
    phrase_words = set()
    for phrase in phrase_keywords:
        phrase_words.update(phrase.split())
    if not phrase_words.isdisjoint(title_words):
        boost += 0.05
    return min(boost, 0.15) # Cap total boost

def clean_section_title(paragraph):
    """
    Cleans and extracts a concise title from a given paragraph.
    """
    match = re.match(r"^([A-Z][^\n:]{3,50}):", paragraph.strip())
    if match:
        return match.group(1).strip()
    lines = paragraph.strip().split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip("•-–●*· ").strip()
        if not line or len(line) < 3 or re.match(r"^[\W\d\s]+$", line):
            continue
        clean_lines.append(line)
        if len(clean_lines) >= 2:
            break
    if not clean_lines:
        return "Untitled Section"
    title = " ".join(clean_lines)
    if "." in title:
        title = title.split(".")[0].strip()
    # if len(title.split()) > 6 and title_rewriter:
    #     try:
    #         rewritten = title_rewriter(f"Make this a clean short title: {title}", max_length=20)[0]['generated_text']
    #         title = rewritten.strip()
    #     except:
    #         pass
    return title[:97] + "..." if len(title) > 100 else title

# --- PENALTY KEYWORD SETS ---
NON_VEG_KEYWORDS = {'chicken', 'pork', 'beef', 'lamb', 'fish', 'shrimp', 'meat', 'prosciutto', 'sausage', 'tuna', 'egg', 'bacon', 'ham', 'salami', 'turkey', 'duck', 'goat', 'veal', 'crab', 'lobster', 'scallops', 'octopus', 'squid', 'calamari', 'shellfish', 'oysters', 'mussels', 'clams', 'caviar', 'anchovies', 'sardines', 'mackerel', 'trout', 'salmon', 'cod', 'haddock', 'halibut', 'tuna', 'swordfish', 'catfish', 'tilapia', 'bass', 'snapper', 'grouper', 'prawns', 'crayfish', 'langoustine', 'crustaceans', 'meats'}
GLUTEN_KEYWORDS = {'wheat', 'flour', 'barley', 'rye', 'bread', 'pasta', 'semolina', 'couscous', 'farina', 'baguette', 'croissant'}

# In src/analyzer.py

def compute_weighted_score(query_embed, para, para_embed, phrase_keywords, simple_keywords, title_boost, filename_keyword_boost, is_veg_request, is_gluten_free_request):
    """
    (Updated) Computes a weighted score with conditional penalties for non-veg or gluten ingredients.
    """
    para_lower = para.lower()
    para_words = set(para_lower.split())

    # --- Conditional Vegetarian Penalty ---
    if is_veg_request and not NON_VEG_KEYWORDS.isdisjoint(para_words):
        return 0 # Disqualify immediately if a meat word is found

    # --- Conditional Gluten Penalty (with check for "gluten-free" exceptions) ---
    if is_gluten_free_request:
        has_gluten_word = False
        for word in GLUTEN_KEYWORDS:
            if word in para_words:
                # Check if the word is part of an exception like "gluten-free flour"
                if f"gluten-free {word}" not in para_lower and f"gluten free {word}" not in para_lower:
                    has_gluten_word = True
                    break
        if has_gluten_word:
            return 0 # Disqualify if a gluten word is found (and it's not an exception)

    # --- Keyword Bonuses (No changes here) ---
    sim_score = util.pytorch_cos_sim(query_embed, para_embed).item()
    phrase_words = set(word for phrase in phrase_keywords for word in phrase.split())
    phrase_bonus = sum(0.05 for keyword in phrase_words if keyword in para_words)
    simple_keyword_bonus = sum(0.10 for keyword in simple_keywords if keyword in para_words)

    return sim_score + phrase_bonus + simple_keyword_bonus + title_boost + filename_keyword_boost


# --- Main Analyzer Function ---

# In src/analyzer.py, replace the entire analyze_persona_job function with this one.
# In src/analyzer.py

# In src/analyzer.py

def analyze_persona_job(parsed_docs, persona, task, challenge_info, all_outlines_data, max_results=8):
    """
    Analyzes documents by extracting full text between headings, correctly handles
    sections that span multiple pages, and includes all scoring features.
    (Optimized for batch processing)
    """
    query = f"{persona['role']} needs to: {task['task']}"
    query_embed = model.encode(query, convert_to_tensor=True, show_progress_bar=False)

    # --- TIERED KEYWORD GENERATION ---
    phrase_keywords = extract_dynamic_keywords(persona, task, challenge_info, top_n=30)
    simple_keywords = extract_keywords_simple(task['task'])
    print(f"Analyzer: Phrase Keywords for context: {phrase_keywords}")
    print(f"Analyzer: Simple Keywords for high-importance bonus: {simple_keywords}")

    # --- NEW: Identify the job constraints from simple keywords ---
    is_veg_request = 'vegetarian' in simple_keywords
    is_gluten_free_request = 'gluten-free' in simple_keywords or 'gluten' in simple_keywords
    
    # --- STEP 1: Collect all sections and their metadata first ---
    sections_to_process = []
    for doc_filename, outline_data in all_outlines_data.items():
        if doc_filename not in parsed_docs:
            continue

        document_text_pages = parsed_docs[doc_filename]
        all_doc_headings = outline_data.get('outline', [])

        filename_keyword_boost = 0
        searchable_filename_title_str = (Path(doc_filename).stem.replace("_", " ") + " " + outline_data.get('title', '')).lower()
        filename_words = set(searchable_filename_title_str.split())
        if not simple_keywords.isdisjoint(filename_words):
            filename_keyword_boost += 0.15
        phrase_words_set = set(word for phrase in phrase_keywords for word in phrase.lower().split())
        if not phrase_words_set.isdisjoint(filename_words):
            filename_keyword_boost += 0.05
        filename_keyword_boost = min(filename_keyword_boost, 0.2)

        for i, current_heading_entry in enumerate(all_doc_headings):
            current_heading_text = current_heading_entry.get('text', '')
            current_page_num = current_heading_entry.get('page', 0) + 1
            if not current_heading_text: continue

            end_page_num = -1
            end_heading_text = None
            is_last_heading_in_doc = (i + 1 >= len(all_doc_headings))

            if not is_last_heading_in_doc:
                next_heading_entry = all_doc_headings[i + 1]
                end_page_num = next_heading_entry.get('page', 0) + 1
                end_heading_text = next_heading_entry.get('text', '')
            else:
                end_page_num = max(document_text_pages.keys()) if document_text_pages else current_page_num

            full_section_text_parts = []
            page_text = document_text_pages.get(current_page_num, "")
            start_index = page_text.find(current_heading_text)
            if start_index == -1: continue

            if current_page_num == end_page_num and end_heading_text:
                end_index = page_text.find(end_heading_text, start_index)
                if end_index == -1: end_index = len(page_text)
                full_section_text_parts.append(page_text[start_index:end_index])
            else:
                full_section_text_parts.append(page_text[start_index:])
                for page_num_in_between in range(current_page_num + 1, end_page_num):
                    full_section_text_parts.append(document_text_pages.get(page_num_in_between, ""))
                if end_page_num > current_page_num:
                    end_page_text = document_text_pages.get(end_page_num, "")
                    end_index = len(end_page_text)
                    if end_heading_text:
                        temp_end_index = end_page_text.find(end_heading_text)
                        if temp_end_index != -1: end_index = temp_end_index
                    full_section_text_parts.append(end_page_text[:end_index])

            full_section_text = "\n".join(full_section_text_parts).strip()
            if len(full_section_text.split()) < 10: continue
            
            # Add the section and its context to a list instead of processing now
            sections_to_process.append({
                'doc_filename': doc_filename,
                'full_section_text': full_section_text,
                'current_heading_text': current_heading_text,
                'current_page_num': current_page_num,
                'level': current_heading_entry.get('level', 'H3'),
                'filename_keyword_boost': filename_keyword_boost
            })

    # --- STEP 2: Perform batch encoding on all collected texts ---
    if not sections_to_process:
        return []

    all_section_texts = [s['full_section_text'] for s in sections_to_process]
    # This one call replaces the hundreds or thousands of calls inside the loop
    all_section_embeddings = model.encode(all_section_texts, convert_to_tensor=True, show_progress_bar=True) 

    # --- STEP 3: Calculate scores using the pre-computed embeddings ---
    potential_sections = []
    for i, section_data in enumerate(sections_to_process):
        para_embed = all_section_embeddings[i]
        final_title = section_data['current_heading_text']
        current_title_boost = boost_from_title(final_title, phrase_keywords, simple_keywords)
        
        calculated_section_score = compute_weighted_score(
            query_embed, section_data['full_section_text'], para_embed,
            phrase_keywords, simple_keywords, current_title_boost, section_data['filename_keyword_boost'],
            is_veg_request=is_veg_request,
            is_gluten_free_request=is_gluten_free_request
        )

        if calculated_section_score > 0.2:
            potential_sections.append({
                'document': section_data['doc_filename'],
                'page_number': section_data['current_page_num'],
                'section_title': final_title,
                'text': section_data['full_section_text'],
                'score': calculated_section_score,
                'level': section_data['level']
            })

    # --- FINAL RANKING LOGIC (No changes here) ---
    all_sections = sorted(potential_sections, key=lambda x: x['score'], reverse=True)
    final_extracted_sections_for_output = []
    doc_count = defaultdict(int)
    current_rank = 1
    for section in all_sections:
        if doc_count[section['document']] >= 3:
            continue
        final_extracted_sections_for_output.append({
            "document": section['document'],
            "section_title": section['section_title'],
            "importance_rank": current_rank,
            "page_number": section['page_number'],
            'score': section['score'],
            'text': section['text']
        })
        doc_count[section['document']] += 1
        current_rank += 1
        if len(final_extracted_sections_for_output) >= max_results:
            break

    return final_extracted_sections_for_output