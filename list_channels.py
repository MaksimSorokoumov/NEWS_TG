import os
import json
import asyncio
import sys
import logging
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel, Chat

# Настройка логирования (можно использовать ту же логику, что в main.py)
class EmojiSafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                stream.write(msg.encode('utf-8', 'replace').decode('utf-8') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/list_channels_log.txt", mode='w', encoding='utf-8'),
        EmojiSafeStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('ListChannelsScript')

# Ensure logs dir
if not os.path.exists("logs"):
    os.makedirs("logs")

def load_config(config_path='config.json'):
    """Загрузка конфигурации из JSON файла."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.critical(f"Ошибка загрузки конфигурации: {e}")
        raise

async def list_dialogs():
    """Получение и вывод списка чатов/каналов."""
    config = load_config()
    
    session_file = os.path.join(
        config['paths']['sessions_dir'],
        f'tg_session_v3_{config["telegram"]["phone"]}'
    )

    client = TelegramClient(
        session_file,
        config['telegram']['api_id'],
        config['telegram']['api_hash'],
        device_model="Desktop",
        system_version="Windows 10",
        app_version="1.0.0",
        lang_code="ru",
        system_lang_code="ru",
        retry_delay=5,
        connection_retries=5,
        auto_reconnect=True,
        sequential_updates=True
    )

    try:
        logger.info("Подключение к Telegram...")
        await client.start(phone=config['telegram']['phone'])

        if not await client.is_user_authorized():
            logger.info("Необходима авторизация!")
            await client.send_code_request(config['telegram']['phone'])
            try:
                code = input('Введите код подтверждения: ')
                await client.sign_in(config['telegram']['phone'], code)
            except SessionPasswordNeededError:
                password = input('Введите пароль двухфакторной аутентификации: ')
                await client.sign_in(password=password)

        logger.info("Авторизация успешна!")

        print("\nСписок ваших чатов, групп и каналов (для добавления в config.json):\n")
        print(f"{'ID':<20} {'Название'}")
        print("-" * 60)

        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, (Channel, Chat)):
                 # Для каналов и групп используем отрицательный ID, если это необходимо для API
                display_id = entity.id
                if isinstance(entity, Channel) and entity.broadcast: # Это публичный или приватный канал
                    display_id = -100 * 10**9 - entity.id # Формат ID для каналов в config.json
                elif isinstance(entity, Chat): # Это группа
                     display_id = -entity.id # Формат ID для групп
                
                # Используем title или name в зависимости от типа
                title = getattr(entity, 'title', getattr(entity, 'name', 'Без названия'))
                print(f"{str(display_id):<20} {title}")

    except Exception as e:
        logger.error(f"Произошла ошибка: {e}", exc_info=True)
    finally:
        if client:
            await client.disconnect()
            logger.info("Клиент Telegram отключен.")

if __name__ == "__main__":
    asyncio.run(list_dialogs())