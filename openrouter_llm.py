import os
import json
import requests
import re

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL_NAME = "deepseek/deepseek-r1:free"
REFERER = "https://yourdomain.com"
TITLE = "HabitCoach"

def extract_json_from_markdown(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(\{[\s\S]+?\})\s*```", content, re.IGNORECASE)
    if match:
        return match.group(1)
    first = content.find('{')
    last = content.rfind('}')
    if first != -1 and last != -1 and last > first:
        return content[first:last+1]
    return content

def generate_motivation(prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": REFERER,
        "X-Title": TITLE,
    }
    data = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        # Try to extract motivational text from JSON
        json_str = extract_json_from_markdown(content)
        obj = json.loads(json_str)
        # Expected format: {"motivation": "Текст..."}
        return obj.get("motivation") or content
    except Exception as e:
        print("LLM API error:", e)
        return "Не удалось получить мотивационное сообщение. Попробуй позже."

