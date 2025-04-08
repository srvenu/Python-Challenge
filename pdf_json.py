import fitz  # PyMuPDF
import pdfplumber
import re
import json
import requests
import pytesseract
from pdf2image import convert_from_path

# ========== CONFIG ==========
# openai and ni keys 
# ============================

# ========== PDF TEXT ==========
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)

# ========== TABLES ==========
def extract_tables_from_pdf(pdf_path):
    cleaned_tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"[INFO] PDF has {len(pdf.pages)} pages.")
            for i, page in enumerate(pdf.pages):
                print(f"[INFO] Processing page {i + 1}")
                tables = page.extract_tables()
                print(f"[DEBUG] Found {len(tables)} table(s)")
                for table in tables:
                    print(f"[DEBUG] Raw Table: {table}")
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
        print("[INFO] No tables found. Trying OCR fallback...")
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

# ========== RULE-BASED PARSER ==========
def build_json(text, tables):
    data = {}

    name_match = re.search(r'Name\s+(\w+)', text)
    date_match = re.search(r'Date\s+(\d{2}/\d{2}/\d{4})', text)
    data['name'] = name_match.group(1) if name_match else None
    data['date'] = date_match.group(1) if date_match else None
    data['tables'] = tables

    story_match = re.search(r'Story\s+(.*?)(?=\n[A-Z]|$)', text, re.DOTALL)
    if story_match:
        lines = story_match.group(1).strip().split('\n')
        if lines:
            data['story'] = {
                "message": lines[0].strip(),
                "actions": [line.strip("• ").strip() for line in lines[1:] if line.strip()]
            }

    return data

# ========== OpenAI (Optional) ==========
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

# ========== Gemini (Fallback) ==========
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

# ========== MAIN PROCESS ==========
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

# ========== SAVE ==========
def save_json(data, filename='output.json'):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved structured JSON to {filename}")

# ========== CLI ==========
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pdf_json.py <file.pdf>")
    else:
        pdf_path = sys.argv[1]
        json_data = process_pdf_to_json(pdf_path)
        save_json(json_data)
