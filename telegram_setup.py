"""
הרץ פעם אחת כדי לקבל TELEGRAM_SESSION string.
לאחר מכן הוסף את המחרוזת כ-environment variable ב-Railway.

שימוש:
  python telegram_setup.py
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = input("הכנס api_id: ").strip()
API_HASH = input("הכנס api_hash: ").strip()

async def main():
    async with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
        await client.start()
        session_string = client.session.save()
        print("\n" + "="*60)
        print("TELEGRAM_SESSION (העתק את כל השורה הבאה ל-Railway):")
        print("="*60)
        print(session_string)
        print("="*60)

asyncio.run(main())
