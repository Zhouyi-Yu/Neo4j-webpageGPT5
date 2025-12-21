import asyncio
import json
from backend import answer_question

async def diagnose():
    question = "who is working on smart grids"
    print(f"Diagnosing question: {question}")
    try:
        result = await answer_question(question)
        print("Result successful!")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Caught expected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(diagnose())
