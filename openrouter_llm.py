import os
import json
from openai import OpenAI

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL_NAME = "deepseek/deepseek-r1:free"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

async def generate_motivations_bulk(count: int):
    """
    Generate motivational messages: count per hardness (easy/medium/hard).
    Returns dict: {"easy": [...], "medium": [...], "hard": [...]}
    """
    prompt = (
        f"Придумай {count} легких, {count} средних и {count} жестких "
        "мотивационных фраз, чтобы бросить курить. "
        "Ответ предоставь строго в следующем формате JSON: "
        "{\"easy\": [\"...\", ...], \"medium\": [\"...\", ...], \"hard\": [\"...\", ...]}"
    )
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
    )
    content = completion.choices[0].message.content
    try:
        result = json.loads(content)
        if all(k in result for k in ("easy", "medium", "hard")):
            return result
    except Exception as e:
        print("LLM JSON parse error:", e)
    return {"easy": [], "medium": [], "hard": []}