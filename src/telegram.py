import os
import json
import signal
import asyncio
import random
from collections import defaultdict
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
NAME = os.getenv('NAME')

# Alustetaan Telegram-client
client = TelegramClient('bot_session', API_ID, API_HASH)

# Muuttuja kontaktien tallentamiseen
contacts_cache = None
contacts_cache_time = 0
CACHE_EXPIRE_TIME = 3600  # 1 tunti sekunteina

# Puskuri viesteille ennen käsittelyä
message_buffer = defaultdict(list)
delay_tasks = {}
read_tasks = {}

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

def calculate_delay_based_on_message_length(text):
    """Laskee viiveen viestin pituuden perusteella"""
    base_delay = random.randint(60, 180)  # Perusviive 1-3 minuuttia
    length_factor = len(text) / 50  # 50 merkkiä = 1x kerroin
    length_delay = min(length_factor * 15, 60)  # Enintään 60 sekuntia lisää
    
    total_delay = base_delay + length_delay
    return int(total_delay)

async def mark_messages_as_read(user_id, messages):
    """Merkitsee viestit luetuksi"""
    try:
        for event in messages:
            await client(functions.messages.ReadHistoryRequest(
                peer=await event.get_input_chat(),
                max_id=event.message.id
            ))
        print(f"Viestit merkitty luetuksi käyttäjälle {user_id}")
    except Exception as e:
        print(f"Virhe viestien lukemisessa käyttäjälle {user_id}: {e}")

async def process_buffered_messages(user_id):
    """Käsittelee puskuroidut viestit käyttäjälle ja lähettää vastauksen"""
    try:
        if user_id not in message_buffer or not message_buffer[user_id]:
            return
            
        # Käsitellään kaikki puskuroidut viestit
        buffered_messages = message_buffer[user_id].copy()
        print(f"Lähetetään vastaus {len(buffered_messages)} viestille käyttäjältä {user_id}")
        
        # Yhdistetään kaikkien viestien tekstit yhdeksi viestiksi
        combined_text = " ".join([event.raw_text for event in buffered_messages])
        
        # Haetaan käyttäjän puhelinnumero (ensimmäisen viestin lähettäjältä)
        sender = await buffered_messages[0].get_sender()
        phone_number = await get_user_phone(sender)
        
        # Viestin tiedot dictionary-muodossa
        message_data = {
            'sender_id': user_id,
            'phone': phone_number,
            'text': combined_text,
            'timestamp': buffered_messages[-1].message.date.isoformat(),  # Viimeisen viestin aika
            'name': NAME
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
            
            # Lähetetään vastaus takaisin käyttäjälle
            reply_msg = f" {response_data.get('message', 'Ei vastausta')}"
            
            # Satunnainen valinta lähetetäänkö vastaus suorana vastauksena vai uutena viestinä
            if random.choice([True, False]):  # 50% todennäköisyys kummallekin
                await buffered_messages[-1].reply(reply_msg)  # Vastaa viimeiseen viestiin
            else:
                # Lähetä uutena viestinä samalle chatille
                await client.send_message(buffered_messages[0].chat_id, reply_msg)
                
            print(f"Vastaus lähetetty käyttäjälle {user_id}")
                
        except requests.exceptions.RequestException as e:
            print(f"Virhe REST-pyynnössä: {e}")
        
        # Poista käsitellyt viestit puskurista
        message_buffer[user_id] = message_buffer[user_id][len(buffered_messages):]
        
    except Exception as e:
        print(f"Virhe vastauksen lähetyksessä käyttäjälle {user_id}: {e}")

async def start_delay_timer(user_id):
    """Käynnistää viiveen ennen viestien käsittelyä"""
    try:
        if user_id not in message_buffer or not message_buffer[user_id]:
            return
            
        # Lasketaan viive viestien pituuden perusteella
        combined_text = " ".join([event.raw_text for event in message_buffer[user_id]])
        total_delay = calculate_delay_based_on_message_length(combined_text)
        read_delay = int(total_delay * 0.7)  # 70% viiveestä merkitään luetuksi
        response_delay = total_delay  # Koko viive vastausta varten
        
        print(f"Odota {read_delay}s lukemiseen ja {response_delay}s vastaamiseen käyttäjälle {user_id}...")
        
        # 1. Odota 70% viivettä ja merkitse viestit luetuksi
        remaining_read_delay = read_delay
        check_interval = 3  # Tarkista uudet viestit joka 3 sekunti
        
        while remaining_read_delay > 0:
            await asyncio.sleep(min(check_interval, remaining_read_delay))
            remaining_read_delay -= check_interval
            
            # Jos uusia viestejä on tullut, keskeytä nykyinen viive ja laske uusi
            current_buffer_size = len(message_buffer[user_id])
            if current_buffer_size > 0:  # Uusia viestejä on tullut
                new_combined_text = " ".join([event.raw_text for event in message_buffer[user_id]])
                new_total_delay = calculate_delay_based_on_message_length(new_combined_text)
                new_read_delay = int(new_total_delay * 0.7)
                
                # Jos uusi viive on pidempi, jatka odotusta uudella viiveellä
                if new_total_delay > total_delay:
                    print(f"Uusia viestejä tullut, jatketaan odotusta {new_total_delay}s...")
                    total_delay = new_total_delay
                    read_delay = new_read_delay
                    response_delay = new_total_delay
                    remaining_read_delay = read_delay
                else:
                    print(f"Uusia viestejä tullut, jatketaan nykyistä odotusta...")
        
        # 2. Merkitse viestit luetuksi (70% kohdalla)
        buffered_messages = message_buffer[user_id].copy()
        await mark_messages_as_read(user_id, buffered_messages)
        
        # 3. Odota loput viivettä vastausta varten
        remaining_response_delay = response_delay - read_delay
        if remaining_response_delay > 0:
            print(f"Odota {remaining_response_delay}s ennen vastaamista...")
            await asyncio.sleep(remaining_response_delay)
        
        # 4. Lähetä vastaus
        await process_buffered_messages(user_id)
        
    except asyncio.CancelledError:
        print(f"Viive keskeytetty käyttäjälle {user_id}")
    except Exception as e:
        print(f"Virhe viiveen aikana käyttäjälle {user_id}: {e}")

@client.on(events.NewMessage)
async def handle_message(event):
    try:
        # Tarkista onko lähettäjä kontaktissa
        sender = await event.get_sender()
        if await is_contact(sender.id):
            print(f"Viesti kontaktilta {sender.id}, ei vastata.")
            return
        
        # Lisää viesti puskuriin
        user_id = sender.id
        message_buffer[user_id].append(event)
        buffer_size = len(message_buffer[user_id])
        print(f"Viesti lisätty puskuriin käyttäjälle {user_id}, puskurin koko: {buffer_size}")
        
        # Keskeytä mahdollinen käynnissä oleva viive ja käynnistä uusi
        if user_id in delay_tasks and not delay_tasks[user_id].done():
            delay_tasks[user_id].cancel()
            try:
                await delay_tasks[user_id]
            except asyncio.CancelledError:
                pass
        
        # Käynnistä uusi viive
        delay_tasks[user_id] = asyncio.create_task(start_delay_timer(user_id))
                
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
