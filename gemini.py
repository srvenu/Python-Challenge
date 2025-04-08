import google.generativeai as genai

genai.configure(api_key=" " # openai and ni keys )

def call_gemini_api(prompt):
    try:
        model = genai.GenerativeModel(model_name="models/gemini-pro")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return None
