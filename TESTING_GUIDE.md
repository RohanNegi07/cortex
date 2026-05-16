#!/usr/bin/env python3
"""
CORTEX System Testing Guide
Test all components locally before connecting to IRIS/CELL/ERP
"""

import asyncio
import json
from datetime import datetime, date
from pathlib import Path

# ============================================================================
# PART 1: START THE CORTEX SERVICE
# ============================================================================
"""
1. Start FastAPI service (in terminal):
   cd c:/Users/rohan/OneDrive/Desktop/project_health_agent_new
   uvicorn cortex.main:app --host 0.0.0.0 --port 8004 --reload

Expected output:
   INFO:     Uvicorn running on http://0.0.0.0:8004
   INFO:     Application startup complete
"""

# ============================================================================
# PART 2: TEST HEALTH CHECK ENDPOINT (No DB needed)
# ============================================================================
"""
2. Test health check:
   curl http://localhost:8004/cortex/health

Expected response (200 OK):
   {"status":"ok","message":"CORTEX is running","database_connected":true,"version":"0.1.0"}
"""

# ============================================================================
# PART 3: SEED TEST DATA INTO DATABASE
# ============================================================================
"""
3. Before testing endpoints, seed test data:
   python load_meetings.py

This loads sample meetings into the database for testing.
"""

# ============================================================================
# PART 4: TEST ENDPOINTS (with curl or Python)
# ============================================================================

TEST_ENDPOINTS = {
    "1_health_check": {
        "method": "GET",
        "url": "http://localhost:8004/cortex/health",
        "description": "Basic health check - no auth needed"
    },
    
    "2_ingest_nerve": {
        "method": "POST",
        "url": "http://localhost:8004/cortex/ingest-nerve",
        "headers": {"X-API-Key": "test-key"},
        "body": {
            "project_id": "acme-crm",
            "meeting_id": "2026-05-23-m1-review",
            "meeting_date": "2026-05-23",
            "meeting_type": "milestone-review"
        },
        "description": "Test NERVE ingest pipeline (7 steps)"
    },
    
    "3_chat": {
        "method": "POST",
        "url": "http://localhost:8004/cortex/chat",
        "headers": {"X-Employee-ID": "p-rohan-001", "X-Project-ID": "acme-crm"},
        "body": {
            "message": "What's the current project status?",
            "conversation_history": []
        },
        "description": "Test chat endpoint with role-aware response"
    },
    
    "4_team_change": {
        "method": "POST",
        "url": "http://localhost:8004/cortex/team-change",
        "headers": {"X-API-Key": "test-key"},
        "body": {
            "project_id": "acme-crm",
            "change_type": "pm_reassignment",
            "outgoing_employee_id": "p-rohan-001",
            "incoming_employee_id": "p-priya-002",
            "effective_date": "2026-05-20"
        },
        "description": "Test KT document generation on PM change"
    },
    
    "5_slack_health_alert": {
        "method": "POST",
        "url": "http://localhost:8004/cortex/slack/health-alert",
        "headers": {"X-API-Key": "test-key"},
        "body": {
            "project_id": "acme-crm",
            "score": 75,
            "band": "amber",
            "old_score": 82
        },
        "description": "Test Slack health alert notification"
    },
    
    "6_document_generation": {
        "method": "POST",
        "url": "http://localhost:8004/cortex/documents",
        "headers": {"X-API-Key": "test-key"},
        "body": {
            "project_id": "acme-crm",
            "doc_type": "status_report"
        },
        "description": "Test document generation with templates"
    }
}

# ============================================================================
# PART 5: PYTHON TEST SCRIPT
# ============================================================================

print("""
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CORTEX SYSTEM TESTING GUIDE                              │
└─────────────────────────────────────────────────────────────────────────────┘

STEP 1: Start the service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Open a terminal and run:

  cd c:/Users/rohan/OneDrive/Desktop/project_health_agent_new
  uvicorn cortex.main:app --host 0.0.0.0 --port 8004 --reload

You should see:
  INFO:     Uvicorn running on http://0.0.0.0:8004
  INFO:     Application startup complete


STEP 2: Seed test data
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
In another terminal, run:

  python load_meetings.py

This loads sample Acme CRM project data into the database.


STEP 3: Test endpoints (choose one method below)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option A: Using curl (command line)
────────────────────────────────────

1. Test health check:
   curl http://localhost:8004/cortex/health

2. Test NERVE ingest:
   curl -X POST http://localhost:8004/cortex/ingest-nerve \\
     -H "X-API-Key: test-key" \\
     -H "Content-Type: application/json" \\
     -d '{
       "project_id": "acme-crm",
       "meeting_id": "2026-05-23-m1-review"
     }'

3. Test chat:
   curl -X POST http://localhost:8004/cortex/chat \\
     -H "X-Employee-ID: p-rohan-001" \\
     -H "X-Project-ID: acme-crm" \\
     -H "Content-Type: application/json" \\
     -d '{
       "message": "What\\'s the project status?",
       "conversation_history": []
     }'


Option B: Using Python requests (easier)
─────────────────────────────────────────

Run:
  python test_cortex.py

This will test all endpoints automatically.


STEP 4: Check database
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Connect to Postgres:
  psql -U cortex_user -d cortex_db -h localhost

Query meetings:
  SELECT project_id, meeting_id, meeting_type FROM meeting_insights;

Query health scores:
  SELECT project_id, score, health_band FROM project_health_scores ORDER BY computed_at DESC;

Query actions:
  SELECT project_id, action_type, status FROM agent_actions;


STEP 5: View logs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watch the uvicorn terminal for:
  ✅ [OK] CORTEX ready
  ✅ Health score computed
  ✅ NERVE pipeline completed
  ❌ Any errors (will appear in red)


WHAT EACH TEST VALIDATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Health check (GET /cortex/health)
   ✓ Service is running
   ✓ Database connection works
   ✓ Lifespan context initialized

2. NERVE ingest (POST /cortex/ingest-nerve)
   ✓ 7-step pipeline executes
   ✓ Health score computed
   ✓ Enriched YAML generated
   ✓ Slack alerts posted (if configured)
   ✓ All actions logged to agent_actions

3. Chat (POST /cortex/chat)
   ✓ Role resolution (pm, apm, ba, director)
   ✓ Semantic retrieval via pgvector
   ✓ LLM response generation
   ✓ Return sources + health score

4. Team change (POST /cortex/team-change)
   ✓ KT document generation
   ✓ R2 upload (if R2 configured)
   ✓ Slack notification (if configured)

5. Slack alert (POST /cortex/slack/health-alert)
   ✓ Message formatting
   ✓ Agent_actions logging
   ✓ Slack API call (if token configured)


EXPECTED RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Health check:        {"status":"ok","message":"CORTEX is running",...}

✅ NERVE ingest:       {"status":"ok","project_id":"acme-crm","health_score":75,...}

✅ Chat:               {"response":"...","sources":[...],"health_score":75}

✅ Team change:        {"status":"ok","project_id":"acme-crm","document_id":"kt_...",...}

✅ Slack alert:        {"status":"ok","message":"Health alert posted to Slack"}


TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ERROR: Connection refused (port 8004)
  → Service not running. Check uvicorn terminal.

ERROR: Database connection failed
  → Postgres not running. Start with: psql or check DATABASE_URL in .env

ERROR: 401 Unauthorized
  → API key mismatch. Make sure X-API-Key header matches CORTEX_API_KEY

ERROR: 404 Not Found
  → Endpoint doesn't exist. Check router registration in main.py

ERROR: 422 Unprocessable Entity
  → Invalid request body. Check JSON format against Pydantic schemas


NEXT STEPS (After local testing)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Configure external services:
   - Set R2 credentials to upload documents
   - Set Slack tokens for notifications
   - Set CELL_API_BASE_URL for velocity summaries

2. Wire up IRIS:
   - Configure IRIS to call POST /cortex/ingest-nerve with real insights.yaml

3. Wire up intranet:
   - Configure intranet to call POST /cortex/chat with employee context
   - Configure intranet to call POST /cortex/team-change on PM changes

4. Deploy to production:
   - Run on proper infrastructure (not localhost)
   - Set up monitoring for agent_actions table
   - Configure scheduler jobs for weekly plans
""")
