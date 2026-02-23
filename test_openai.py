from openai import AzureOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
)

response = client.chat.completions.create(
    model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),  # your deployment name, e.g. "gpt-4o-mini"
    messages=[
        {"role": "user", "content": "Say hello"}
    ]
)

print(response.choices[0].message.content)
