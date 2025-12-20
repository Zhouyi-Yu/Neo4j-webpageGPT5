import os
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

async def test_key():
    load_dotenv(override=True)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    print(f"Key loaded (first 10): {api_key[:10]}...")
    print(f"Key loaded (last 4): ...{api_key[-4:]}")
    
    client = AsyncOpenAI(api_key=api_key)
    try:
        # Simple completion to verify key and model access
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}]
        )
        print(f"Success! Response: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"Auth failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_key())
