import os

# Keep secrets in Render/local environment variables. Never hard-code API keys.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
