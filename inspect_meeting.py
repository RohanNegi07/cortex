import sys, os
os.chdir(r'C:\Users\rohan\OneDrive\Desktop\project_health_agent_new')
sys.path.insert(0, os.getcwd())
from cortex.models.db import init_db, close_db, get_connection, release_connection
from dotenv import load_dotenv
load_dotenv('cortex/.env')
import asyncio
async def main():
    ok = await init_db()
    print('init', ok)
    conn = await get_connection()
    rows = await conn.fetch('select id, project_id, meeting_id from meeting_insights where meeting_id in ($1,$2,$3)', '2026-03-05-discovery','2026-05-23-m1-review','2026-06-19-sprint06')
    print([dict(r) for r in rows])
    await release_connection(conn)
    await close_db()
asyncio.run(main())
