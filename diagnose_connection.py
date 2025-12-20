
import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI
from neo4j import AsyncGraphDatabase

async def check_connectivity():
    load_dotenv()
    
    # 1. Check OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"OPENAI_API_KEY: {'[SET]' if api_key else '[NOT SET]'}")
    
    if api_key:
        client = AsyncOpenAI(api_key=api_key)
        try:
            print("Checking OpenAI connectivity...")
            await client.models.list()
            print("OpenAI connectivity: [OK]")
        except Exception as e:
            print(f"OpenAI connectivity: [FAILED] - {type(e).__name__}: {e}")
    
    # 2. Check Neo4j
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    
    print(f"Neo4j URI: {uri}")
    print(f"Neo4j User: {user}")
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))
    try:
        print("Checking Neo4j connectivity...")
        async with driver.session() as session:
            await session.run("RETURN 1")
        print("Neo4j connectivity: [OK]")
    except Exception as e:
        print(f"Neo4j connectivity: [FAILED] - {type(e).__name__}: {e}")
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(check_connectivity())
