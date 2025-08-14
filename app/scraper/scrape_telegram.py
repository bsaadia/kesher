from telethon import TelegramClient
from datetime import datetime, timezone
import asyncio
from bidi.algorithm import get_display


# Replace with your API credentials
API_ID = 'REDACTED_API_ID'
API_HASH = 'REDACTED_API_HASH'
PHONE = 'REDACTED_PHONE'

async def query_channel_messages(channel_username, start_date, end_date):
    client = TelegramClient('session', API_ID, API_HASH)
    
    await client.start(phone=PHONE)
    
    messages = []
    async with client.takeout() as takeout:
        count = 0
        async for message in takeout.iter_messages(
            channel_username,
            offset_date=end_date
        ):
            count += 1
            print(f"Message {count}: {message.date}")
            
            if message.date < start_date:
                break
            if start_date <= message.date <= end_date:
                messages.append({
                    'id': message.id,
                    'date': message.date,
                    'text': message.text,
                    'sender_id': message.sender_id
                })
    
    await client.disconnect()
    return messages

# Usage
async def main():
    channel = '@idf_telegram'
    start = datetime(2025, 8, 13, tzinfo=timezone.utc)
    end = datetime(2025, 8, 13, 23, 59, 59, tzinfo=timezone.utc)
    
    messages = await query_channel_messages(channel, start, end)
    
    filename = f"telegram_messages_{start.strftime('%Y%m%d')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        for msg in messages:
            if msg['text']:
                f.write(f"{msg['date']}: {get_display(msg['text'])}\n\n")
    
    print(f"Saved {len(messages)} messages to {filename}")

if __name__ == '__main__':
    asyncio.run(main())