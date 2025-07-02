import openai
from django.conf import settings
import json

def extract_guest_counts_with_gpt(appointment_data):
    """
    Uses OpenAI GPT to extract adult and kid counts from messy appointment data.
    """
    openai.api_key = settings.OPENAI_API_KEY

    prompt = (
        "Given the following appointment data, extract the number of adults and kids. "
        "If the information is not present, return 0 for each. "
        "Respond in JSON format: {\"adults\": <number>, \"kids\": <number>}\n\n"
        f"Appointment data:\n{appointment_data}\n"
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant for extracting structured data from messy text."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=50,
        temperature=0
    )
    try:
        content = response['choices'][0]['message']['content']
        data = json.loads(content)
        return data.get('adults', 0), data.get('kids', 0)
    except Exception:
        return 0, 0 