import os
import json
import signal
import asyncio
import random
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions
from telethon.tl.types import User
import requests

# Ladataan ympäristömuuttujat
load_dotenv()
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
REST_URL = os.getenv('REST_URL')
PHONE = os.getenv('PHONE')

# Alustetaan Telegram-client
client = TelegramClient('bot_session', API_ID, API_HASH)

# Muuttuja kontaktien tallentamiseen
contacts_cache = None
contacts_cache_time = 0
CACHE_EXPIRE_TIME = 3600  # 1 tunti sekunteina

async def shutdown(signal, loop):
    """Siisti sulkeminen"""
    print(f"Saatiin signaali {signal.name}, suljetaan...")
    await client.disconnect()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def get_user_phone(user):
    """Yritetään hakea käyttäjän puhelinnumero"""
    try:
        if isinstance(user, User):
            if user.phone:
                return user.phone
        return None
    except Exception as e:
        print(f"Virhe puhelinnumeron haussa: {e}")
        return None

async def is_contact(user_id):
    """Tarkistaa onko käyttäjä kontaktilistalla"""
    global contacts_cache, contacts_cache_time
    
    # Käytä välimuistia jos se on ajantasalla
    current_time = asyncio.get_event_loop().time()
    if contacts_cache is not None and (current_time - contacts_cache_time) < CACHE_EXPIRE_TIME:
        return user_id in contacts_cache
    
    try:
        # Hae kontaktit uudestaan
        result = await client(functions.contacts.GetContactsRequest(hash=0))
        contacts_cache = {user.id for user in result.users}
        contacts_cache_time = current_time
        return user_id in contacts_cache
    except Exception as e:
        print(f"Virhe kontaktien haussa: {e}")
        return False

@client.on(events.NewMessage)
async def handle_message(event):
    try:
        # Tarkista onko lähettäjä kontaktissa
        sender = await event.get_sender()
        if await is_contact(sender.id):
            print(f"Viesti kontaktilta {sender.id}, ei vastata.")
            return
        read_delay = random.randint(5, 25)
        print(f"Odota {read_delay} sekuntia ennen viestin lukemista...")
        await asyncio.sleep(read_delay)
        # Merkitse viesti luetuksi
        await client(functions.messages.ReadHistoryRequest(
            peer=await event.get_input_chat(),
            max_id=event.message.id
        ))
        
        # Haetaan käyttäjän puhelinnumero
        phone_number = await get_user_phone(sender)
        
        # Viestin tiedot dictionary-muodossa
        message_data = {
            'sender_id': event.sender_id,
            'phone': phone_number,
            'text': event.raw_text,
            'timestamp': event.message.date.isoformat()
        }

        # Tallennetaan JSON-tiedostoon
        with open('messages.json', 'a', encoding='utf-8') as f:
            json.dump(message_data, f, ensure_ascii=False)
            f.write('\n')

        # Lähetetään data REST-rajapintaan
        try:
            response = requests.post(REST_URL, json=message_data, timeout=10)
            response.raise_for_status()
            response_data = response.json()
            
            # Lisätään satunnainen viive (15-60 sekuntia)
            delay = random.randint(15, 60)
            print(f"Odota {delay} sekuntia ennen vastauksen lähetystä...")
            await asyncio.sleep(delay)
            
            # Lähetetään vastaus takaisin käyttäjälle
            reply_msg = f" {response_data.get('message', 'Ei vastausta')}"
            # Satunnainen valinta lähetetäänkö vastaus suorana vastauksena vai uutena viestinä
            if random.choice([True, False]):  # 50% todennäköisyys kummallekin
                await event.reply(reply_msg)  # Vastaa suoraan viestiin
            else:
                # Lähetä uutena viestinä samalle chatille
                await client.send_message(event.chat_id, reply_msg)
        except requests.exceptions.RequestException as e:
            print(f"Virhe REST-pyynnössä: {e}")
    except Exception as e:
        print(f"Virhe viestin käsittelyssä: {e}")

async def main():
    # Käsitellään sulkemissignaalit
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, loop)))
    
    try:
        # Kirjaudutaan sisään puhelinnumerolla
        await client.start(phone=PHONE)
        print("Botti käynnistetty. Paina Ctrl+C lopettaaksesi.")
        await client.run_until_disconnected()
    except Exception as e:
        print(f"Virhe botin suorituksessa: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
        print("Botti suljettu.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Botti suljettu käyttäjän toimesta.")
    except Exception as e:
        print(f"Odottamaton virhe: {e}")
