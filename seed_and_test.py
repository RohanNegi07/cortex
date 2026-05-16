"""
CORTEX Local Test Script
========================
Run this from your project root:
    python seed_and_test.py

What it does:
  1. Seeds the DB with a real project (acme-crm) and a client
  2. Inserts your 3 meetings from the CSV into meeting_insights
  3. Fires the full 7-step pipeline on the first meeting
  4. Prints the health score result

Requirements:
  - Server does NOT need to be running (calls services directly)
  - Just needs: DATABASE_URL in .env and ANTHROPIC_API_KEY (optional)
"""

import asyncio
import json
import sys
import os
from datetime import date
# Add project root to path so cortex imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cortex.models.db import init_db, close_db, init_schema, get_connection, release_connection
from dotenv import load_dotenv
load_dotenv("cortex/.env")

# ─── Your real meeting data from the CSV ─────────────────────────────────────

MEETINGS = [
    {
        "meeting_id": "2026-03-05-discovery",
        "project_id": "acme-crm",
        "meeting_type": "client-call",
        "meeting_date": "2026-03-05",
        "raw_yaml": {
            "meeting_type": "client-call",
            "meeting_date": "2026-03-05",
            "meeting_id": "2026-03-05-discovery",
            "project_id": "acme-crm",
            "summary": "Client discovery for CRM Field Agent project. Acme field team doing triple data entry (WhatsApp, Excel, Salesforce). Need integrated mobile solution. Client waiting 2 years for this. Team of 3-4 field agents.",
            "risks": [
                {
                    "id": "r001",
                    "description": "Two-year wait could set expectations high",
                    "severity": "medium",
                    "raised_date": "2026-03-05"
                },
                {
                    "id": "r002",
                    "description": "Complex Salesforce Classic integration needed",
                    "severity": "high",
                    "raised_date": "2026-03-05"
                }
            ],
            "blockers": [],
            "sentiment": {
                "score": 0.75,
                "label": "positive",
                "drivers": ["client engaged", "clear problem statement"]
            },
            "milestones": [
                {
                    "name": "Discovery Sign-off",
                    "due_date": "2026-03-20",
                    "status": "completed"
                }
            ]
        }
    },
    {
        "meeting_id": "2026-05-23-m1-review",
        "project_id": "acme-crm",
        "meeting_type": "milestone-review",
        "meeting_date": "2026-05-23",
        "raw_yaml": {
            "meeting_type": "milestone-review",
            "meeting_date": "2026-05-23",
            "meeting_id": "2026-05-23-m1-review",
            "project_id": "acme-crm",
            "summary": "Milestone 1 review. Mobile app MVP demo completed. Client happy with field agent flow. Salesforce sync has a delay issue. API rate limiting causing data loss.",
            "risks": [
                {
                    "id": "r003",
                    "description": "Salesforce API rate limiting causing data sync delays",
                    "severity": "high",
                    "raised_date": "2026-05-23"
                }
            ],
            "blockers": [
                {
                    "description": "Salesforce Classic API credentials not provided by client IT team",
                    "raised_date": "2026-05-20"
                }
            ],
            "sentiment": {
                "score": 0.55,
                "label": "neutral",
                "drivers": ["demo went well", "blocker causing concern"]
            },
            "milestones": [
                {
                    "name": "MVP Mobile App",
                    "due_date": "2026-05-23",
                    "status": "completed"
                },
                {
                    "name": "Salesforce Integration",
                    "due_date": "2026-06-15",
                    "status": "at_risk"
                }
            ]
        }
    },
    {
        "meeting_id": "2026-06-19-sprint06",
        "project_id": "acme-crm",
        "meeting_type": "internal",
        "meeting_date": "2026-06-19",
        "raw_yaml": {
            "meeting_type": "internal",
            "meeting_date": "2026-06-19",
            "meeting_id": "2026-06-19-sprint06",
            "project_id": "acme-crm",
            "summary": "Sprint 6 internal review. Salesforce blocker still unresolved after 30 days. Team morale dipping. Two devs reassigned temporarily. Risk of missing final delivery.",
            "risks": [
                {
                    "id": "r004",
                    "description": "Final delivery at risk due to ongoing Salesforce blocker",
                    "severity": "high",
                    "raised_date": "2026-06-19"
                }
            ],
            "blockers": [
                {
                    "description": "Salesforce Classic API credentials not provided by client IT team",
                    "raised_date": "2026-05-20"
                }
            ],
            "sentiment": {
                "score": 0.30,
                "label": "negative",
                "drivers": ["blocker unresolved 30 days", "team resources reduced"]
            },
            "milestones": [
                {
                    "name": "Salesforce Integration",
                    "due_date": "2026-06-30",
                    "status": "at_risk"
                }
            ]
        }
    }
]


# ─── STEP 1: Seed DB ─────────────────────────────────────────────────────────

async def seed_database():
    print("\n========================================")
    print("  STEP 1: Seeding database")
    print("========================================")

    conn = await get_connection()
    try:
        # Create client
        client_id = await conn.fetchval("""
            INSERT INTO clients (client_name, erp_client_id, industry, relationship_status)
            VALUES ('Acme Corp', 'acme-001', 'Field Services', 'active')
            ON CONFLICT (erp_client_id) DO UPDATE SET client_name = EXCLUDED.client_name
            RETURNING id
        """)
        print(f"✓ Client created: {client_id}")

        # Create project
        project_id = str(await conn.fetchval("""
            INSERT INTO projects (
                erp_project_id, client_id, project_name, project_type,
                pm_employee_id, status, start_date, end_date
            )
            VALUES (
                'acme-crm', $1, 'Acme CRM Field Agent', 'client',
                'pm-rohan-001', 'active', $2, $3
            )
            ON CONFLICT (erp_project_id) DO UPDATE SET status = 'active'
            RETURNING id
        """, client_id, date.fromisoformat('2026-03-01'), date.fromisoformat('2026-07-31')))
        print(f"✓ Project created: {project_id}")

        # Create project_memory placeholder
        await conn.execute("""
        INSERT INTO project_memory (project_id, recent_context, updated_at)
        VALUES ($1, '{"meetings": []}', NOW())
        ON CONFLICT (project_id) DO NOTHING
    """, str(project_id))

        # Insert milestones
        milestones = [
            ("Discovery Sign-off", "2026-03-20", "2026-03-20", "completed"),
            ("MVP Mobile App", "2026-05-23", "2026-05-23", "completed"),
            ("Salesforce Integration", "2026-06-10", "2026-06-30", "at_risk"),
            ("Final Delivery", "2026-07-15", "2026-07-31", "in_progress"),
        ]
        for name, original, current, status in milestones:
            existing_milestone = await conn.fetchrow(
                """
                SELECT id FROM project_milestones
                WHERE project_id = $1 AND name = $2
                """,
                str(project_id), name
            )
            if existing_milestone:
                print(f"  ↳ Milestone '{name}' already exists, skipping")
                continue

            await conn.execute("""
            INSERT INTO project_milestones (
                project_id, name, original_due_date,
                current_due_date, status
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (project_id, name) DO NOTHING
        """, str(project_id), name, date.fromisoformat(original), date.fromisoformat(current), status)

        # Insert meetings
        for m in MEETINGS:
            existing = await conn.fetchrow(
                "SELECT id, project_id FROM meeting_insights WHERE meeting_id = $1", m["meeting_id"]
            )
            if existing:
                if str(existing["project_id"]) != str(project_id):
                    print(f"  ↳ Meeting {m['meeting_id']} exists with wrong project_id; repairing row")
                    await conn.execute("""
                        UPDATE meeting_insights
                        SET project_id = $1,
                            meeting_type = $2,
                            meeting_date = $3,
                            raw_yaml = $4
                        WHERE id = $5
                    """,
                        str(project_id),
                        m["meeting_type"],
                        date.fromisoformat(m["meeting_date"]),
                        json.dumps(m["raw_yaml"]),
                        existing["id"]
                    )
                else:
                    print(f"  ↳ Meeting {m['meeting_id']} already exists, skipping")
                continue

            await conn.execute("""
                INSERT INTO meeting_insights (
                    project_id, meeting_id, meeting_type, meeting_date, raw_yaml
                ) VALUES ($1, $2, $3, $4, $5)
            """,
                str(project_id),
                m["meeting_id"],
                m["meeting_type"],
                date.fromisoformat(m["meeting_date"]),
                json.dumps(m["raw_yaml"])
            )
            print(f"✓ Meeting inserted: {m['meeting_id']}")

        return str(project_id)
    finally:
        await release_connection(conn)


# ─── STEP 2: Run pipeline on each meeting ────────────────────────────────────

async def run_pipeline(project_id: str):
    print("\n========================================")
    print("  STEP 2: Running 7-step pipeline")
    print("========================================")

    from cortex.services.memory import stitch_meeting_memory
    from cortex.services.narrative import update_narrative
    from cortex.services.health import compute_health_score
    from cortex.services.drift import detect_milestone_drift

    conn = await get_connection()
    try:
        meetings = await conn.fetch("""
            SELECT id, meeting_id FROM meeting_insights
            WHERE project_id = $1
            ORDER BY meeting_date ASC
        """, project_id)
    finally:
        await release_connection(conn)

    print(f"  → meetings found: {len(meetings)}")
    if not meetings:
        print("  ⚠ No meetings found for this project_id. Existing meeting rows may be linked to a different project record.")

    for meeting in meetings:
        insight_id = meeting["id"]
        meeting_id = meeting["meeting_id"]
        print(f"\n── Processing: {meeting_id}")

        # Step 2: Memory stitch
        result = await stitch_meeting_memory(project_id, insight_id)
        if result:
            print(f"  ✓ Step 2: Memory stitched")
        else:
            print(f"  ✗ Step 2: Memory stitch failed")

        # Step 3: Narrative (needs ANTHROPIC_API_KEY)
        result = await update_narrative(project_id)
        if result:
            print(f"  ✓ Step 3: Narrative → trend: {result.get('trend')}")
        else:
            print(f"  ✗ Step 3: Narrative failed (check ANTHROPIC_API_KEY)")

        # Step 4: Health score
        result = await compute_health_score(project_id, insight_id)
        if result:
            print(f"  ✓ Step 4: Health score = {result['score']}/100 ({result['band'].upper()})")
            print(f"           Components: {result['components']}")
        else:
            print(f"  ✗ Step 4: Health score failed")

        # Step 5: Milestone drift
        result = await detect_milestone_drift(project_id)
        if result:
            print(f"  ✓ Step 5: Drift check — {result['drifted_count']} milestones drifted")
        else:
            print(f"  ✗ Step 5: Drift check failed")


# ─── STEP 3: Print final state ───────────────────────────────────────────────

async def print_results(project_id: str):
    print("\n========================================")
    print("  STEP 3: Final state in DB")
    print("========================================")

    conn = await get_connection()
    try:
        # Latest health score
        health = await conn.fetchrow("""
            SELECT score, band, components, computed_at
            FROM project_health_scores
            WHERE project_id = $1
            ORDER BY computed_at DESC LIMIT 1
        """, project_id)

        if health:
            print(f"\n🏥 HEALTH SCORE")
            print(f"   Score : {health['score']}/100")
            print(f"   Band  : {health['band'].upper()}")
            print(f"   Time  : {health['computed_at']}")
        else:
            print("\n⚠ No health score computed")

        # Memory state
        memory = await conn.fetchrow("""
            SELECT sentiment_history, risk_register, blocker_log,
                   relationship_trajectory
            FROM project_memory WHERE project_id = $1
        """, project_id)

        if memory:
            sentiment = json.loads(memory["sentiment_history"] or "[]")
            risks = json.loads(memory["risk_register"] or "[]")
            blockers = json.loads(memory["blocker_log"] or "[]")
            trajectory = json.loads(memory["relationship_trajectory"] or "{}")

            print(f"\n🧠 PROJECT MEMORY")
            print(f"   Sentiment entries : {len(sentiment)}")
            print(f"   Open risks        : {len([r for r in risks if r.get('status') == 'open'])}")
            print(f"   Unresolved blockers: {len([b for b in blockers if not b.get('resolved_date')])}")
            print(f"   Relationship trend: {trajectory.get('trend', 'N/A')}")
            if trajectory.get("narrative"):
                print(f"   Narrative: {trajectory['narrative'][:150]}...")

        # Milestones
        milestones = await conn.fetch("""
            SELECT name, status, original_due_date, current_due_date
            FROM project_milestones WHERE project_id = $1
        """, project_id)

        print(f"\n📅 MILESTONES")
        for m in milestones:
            drift = (m["current_due_date"] - m["original_due_date"]).days
            drift_str = f" (+{drift}d drift)" if drift > 0 else ""
            print(f"   {m['name']:<30} {m['status']:<15}{drift_str}")
    finally:
        await release_connection(conn)

    print("\n========================================")
    print("  ALL DONE ✓")
    print("========================================\n")


# ─── MAIN ────────────────────────────────────────────────────────────────────

async def main():
    print("\n🚀 CORTEX Local Test — Acme CRM Project")

    # Init DB
    ok = await init_db()
    if not ok:
        print("❌ Could not connect to DB. Check DATABASE_URL in cortex/.env")
        return

    await init_schema()

    # Run
    project_id = await seed_database()
    await run_pipeline(project_id)
    await print_results(project_id)

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())