# src/utils.py
from datetime import datetime
import json

def load_input(path):
    with open(path) as f:
        return json.load(f)

def generate_output_json(input_data, sections, subsections, output_path):
    output = {
        "metadata": {
            "input_documents": [doc['filename'] for doc in input_data['documents']],
            "persona": input_data['persona']['role'],
            "job_to_be_done": input_data['job_to_be_done']['task'],
            "processing_timestamp": datetime.now().isoformat()
        },
        "extracted_sections": sections,
        "subsection_analysis": subsections
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)