"""Fix thread snippets — recompute last_snippet from last message with proper stripping.

Run: /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/fix_thread_snippets.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from src.core.database import get_db_context
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature


async def fix():
    async with get_db_context() as db:
        threads = (await db.execute(select(AgentThread))).scalars().all()
        fixed = 0
        for thread in threads:
            msgs = (await db.execute(
                select(AgentMessage)
                .where(AgentMessage.thread_id == thread.id)
                .order_by(AgentMessage.received_at)
            )).scalars().all()
            if not msgs:
                continue
            last = msgs[-1]
            clean = strip_email_signature(strip_quoted_reply(last.body or ""))[:200]
            if clean != thread.last_snippet:
                thread.last_snippet = clean
                fixed += 1
        await db.commit()
        print(f"Fixed {fixed} of {len(threads)} thread snippets")


if __name__ == "__main__":
    asyncio.run(fix())
