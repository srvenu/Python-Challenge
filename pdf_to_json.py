import fitz
import pdfplumber
import re
import json
import requests
import pytesseract
from pdf2image import convert_from_path

# openai and ni keys 

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)

def extract_tables_from_pdf(pdf_path):
    extracted = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    flat_rows = [row for row in table if any(row)]
                    if len(flat_rows) >= 2:
                        if flat_rows[0][0].lower() == "name":
                            headers = flat_rows[2]
                            data_rows = flat_rows[3:-1]
                            cleaned = []
                            for row in data_rows:
                                if len(row) == len(headers):
                                    cleaned.append({headers[i]: (row[i] or "").strip() for i in range(len(headers))})
                            if cleaned:
                                extracted.append({"Categories": cleaned})
        if extracted:
            return extracted
    except Exception as e:
        print("Table extraction failed:", e)

    return extract_tables_with_ocr(pdf_path)

def extract_tables_with_ocr(pdf_path):
    images = convert_from_path(pdf_path)
    all_rows = []
    for img in images:
        text = pytesseract.image_to_string(img)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            cells = re.split(r'\s{2,}|\t|\s{4,}', line)  # More flexible splitting
            if len(cells) > 1:
                row = {f"col_{i+1}": val.strip() for i, val in enumerate(cells)}
                all_rows.append(row)
    return [{"Categories": all_rows}] if all_rows else []

def extract_flowchart(text):
    lines = text.split('\n')
    flow_lines = []
    capture = False
    for i, line in enumerate(lines):
        if 'Mapping the Flow' in line:
            capture = True
            continue
        if capture:
            if re.match(r'^[A-Z][a-z\s\-]+$', line.strip()) and not line.strip().startswith("Story"):
                flow_lines.append(line.strip())
            if 'Story' in line:
                break
    return {"Mapping the Flow": flow_lines} if flow_lines else {}

def extract_story(text):
    story_match = re.search(r'Story\s+(.*?)(?=\n[A-Z][a-zA-Z ]+:|$)', text, re.DOTALL)
    if story_match:
        lines = story_match.group(1).strip().split('\n')
        if lines:
            return {
                "Story": {
                    "message": lines[0].strip(),
                    "actions": [line.strip("• ").strip() for line in lines[1:] if line.strip()]
                }
            }
    return {}

def extract_name_and_date(text):
    name_match = re.search(r'Name\s+(\w+)', text)
    date_match = re.search(r'Date\s+(\d{2}/\d{2}/\d{4})', text)
    return {
        "name": name_match.group(1) if name_match else None,
        "date": date_match.group(1) if date_match else None
    }

def build_json(text, tables):
    data = extract_name_and_date(text)
    for table in tables:
        data.update(table)
    data.update(extract_flowchart(text))
    data.update(extract_story(text))
    return data

def process_pdf_to_json(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    tables = extract_tables_from_pdf(pdf_path)
    return build_json(text, tables)

def save_json(data, filename='output.json'):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved structured JSON to {filename}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_json.py <file.pdf>")
    else:
        pdf_path = sys.argv[1]
        result = process_pdf_to_json(pdf_path)
        save_json(result)
