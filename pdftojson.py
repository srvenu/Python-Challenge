import fitz  # PyMuPDF
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
    cleaned_tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 2:
                        for idx, row in enumerate(table):
                            if all(cell is not None and str(cell).strip() != "" for cell in row):
                                headers = row
                                body = table[idx + 1:]
                                rows = []
                                for row in body:
                                    if row and len(row) == len(headers):
                                        row_data = {headers[i]: row[i] for i in range(len(headers))}
                                        rows.append(row_data)
                                if rows:
                                    cleaned_tables.append(rows)
                                break
    except Exception as e:
        print("Table extraction failed:", e)

    if not cleaned_tables:
        cleaned_tables = extract_tables_with_ocr(pdf_path)

    return cleaned_tables

def extract_tables_with_ocr(pdf_path):
    images = convert_from_path(pdf_path)
    all_rows = []

    for img in images:
        text = pytesseract.image_to_string(img)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            cells = re.split(r'\s{2,}|\t', line)
            if len(cells) > 1:
                row_data = {f"col_{i + 1}": cell for i, cell in enumerate(cells)}
                all_rows.append(row_data)

    return [all_rows] if all_rows else []

def extract_flowchart(text):
    lines = text.split('\n')
    flow_lines = []
    capture = False
    for line in lines:
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
    data['tables'] = tables
    data.update(extract_flowchart(text))
    data.update(extract_story(text))
    return data

def extract_json_with_openai(text):
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        prompt = f"Convert the following PDF content into structured JSON:\n\n{text}"
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        content = response.choices[0].message["content"]
        return json.loads(content)
    except Exception as e:
        print("OpenAI API failed:", e)
        return None

def extract_json_with_gemini(text):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "parts": [{"text": f"Convert the following PDF content to structured JSON:\n\n{text}"}]
            }]
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(url, headers=headers, json=payload)
        res_json = res.json()
        raw = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "")
        return json.loads(raw)
    except Exception as e:
        print("Gemini API failed:", e)
        return None

def process_pdf_to_json(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    tables = extract_tables_from_pdf(pdf_path)

    print("[INFO] Trying OpenAI...")
    result = extract_json_with_openai(text)
    if result:
        return result

    print("[INFO] Trying Gemini...")
    result = extract_json_with_gemini(text)
    if result:
        return result

    print("[INFO] Using fallback rule-based parser...")
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
