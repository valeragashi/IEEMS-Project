from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
_client = OpenAI()   # reads OPENAI_API_KEY from the environment


def extract_structured(system_prompt: str, user_text: str, schema):
    #The pipeline's only LLM call. Returns a parsed pydantic model (LLMReceipt)

    completion = _client.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        response_format=schema,
    )
    msg = completion.choices[0].message
    if msg.refusal:
        raise ValueError(f"Model refused: {msg.refusal}")
    return msg.parsed