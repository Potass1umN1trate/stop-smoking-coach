import os
import json
import requests
import re

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL_NAME = "deepseek/deepseek-r1:free"
REFERER = "https://yourdomain.com"  # Optional, can be blank or set to your own site
TITLE = "StopSmokingCoach"          # Optional

def extract_json_from_markdown(content: str) -> str:
    """
    Strips markdown code fences (like ```json ... ```) from LLM output, returns JSON string.
    """
    # Regex for code block: ```(json)? ... ```
    match = re.search(r"```(?:json)?\s*(\{[\s\S]+?\})\s*```", content, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: if no code block, try to find the first '{' and last '}'
    first = content.find('{')
    last = content.rfind('}')
    if first != -1 and last != -1 and last > first:
        return content[first:last+1]
    # As last resort, return as is (will likely fail json.loads)
    return content

def generate_motivations_bulk(count: int):
    """
    Synchronously generates motivational messages from OpenRouter API.
    Returns: {"easy": [...], "medium": [...], "hard": [...]}
    """
    prompt = (
        f"Придумай {count} легких, {count} средних и {count} жестких "
        "мотивационных фраз, чтобы бросить курить. "
        "Ответ предоставь строго в следующем формате JSON: "
        "{\"easy\": [\"...\", ...], \"medium\": [\"...\", ...], \"hard\": [\"...\", ...]}"
    )
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
        json_str = extract_json_from_markdown(content)
        result = json.loads(json_str)
        if all(k in result for k in ("easy", "medium", "hard")):
            return result
    except Exception as e:
        print("LLM API error:", e)
    return {"easy": [], "medium": [], "hard": []}
