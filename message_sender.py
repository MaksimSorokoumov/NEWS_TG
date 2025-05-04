import os
import json
import logging
import sys
import asyncio
import requests
import re
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import InputPeerUser, InputPeerChannel
from media_handler import MediaHandler

# Настройка логирования
class EmojiSafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Безопасно заменяем неподдерживаемые символы
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
        logging.FileHandler("logs/sender_log.txt", mode='w', encoding='utf-8'),
        EmojiSafeStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('MessageSender')

# Ensure logs directory exists
if not os.path.exists("logs"):
    os.makedirs("logs")

class MessageSender:
    def __init__(self, config_path='config.json'):
        """Инициализация отправителя сообщений."""
        self.config = self._load_config(config_path)
        self.data_dir = self.config['paths']['data_dir']
        self.client = None
        self.session_file = os.path.join(
            self.config['paths']['sessions_dir'], 
            f'tg_session_v3_{self.config["telegram"]["phone"]}'
        )
        self.bot_token = self.config['telegram']['bot_token']
        self.user_id = self.config['telegram']['user_id']
        self.direct_forward = self.config.get('app', {}).get('direct_forward', True)
        self.wait_delay = 1.0  # Задержка между сообщениями
        self.media_handler = None
        
    def _load_config(self, config_path):
        """Загрузка конфигурации из JSON файла."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            logger.critical(f"Ошибка загрузки конфигурации: {e}")
            raise

    def load_unique_messages(self):
        """Загрузка списка уникальных сообщений для отправки."""
        messages_file = os.path.join(self.data_dir, 'unique_messages.json')
        
        if not os.path.exists(messages_file):
            logger.warning(f"Файл с уникальными сообщениями не найден: {messages_file}")
            return None
            
        try:
            with open(messages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                messages = data.get('messages', [])
                timestamp = data.get('timestamp', '')
                
            logger.info(f"Загружено {len(messages)} уникальных сообщений от {timestamp}")
            return messages
        except Exception as e:
            logger.error(f"Ошибка загрузки уникальных сообщений: {e}")
            return None

    async def initialize_client(self):
        """Инициализация и авторизация клиента Telegram."""
        logger.info("Инициализация клиента Telegram...")
        self.client = TelegramClient(
            self.session_file, 
            self.config['telegram']['api_id'], 
            self.config['telegram']['api_hash'],
            device_model="Desktop",
            system_version="Windows 10",
            app_version="1.0.0"
        )

        try:
            await self.client.start()
            if not await self.client.is_user_authorized():
                logger.error("Клиент не авторизован, требуется запустить telegram_downloader.py")
                return False
                
            logger.info("Авторизация успешна!")
            # Инициализируем обработчик медиа
            self.media_handler = MediaHandler(self.client, self.config)
            return True
        except Exception as e:
            logger.error(f"Ошибка при авторизации: {e}")
            return False

    async def send_message_via_bot(self, user_id, text):
        """Отправка сообщения через Telegram Bot API используя Markdown."""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        # Текст с Markdown (header + body)
        md_text = text
        # Обрезка до лимита (4096 символов)
        if len(md_text) > 4000:
            logger.info(f"Сообщение слишком длинное ({len(md_text)}), обрезаем до 4000")
            header_end = md_text.find("\n\n")
            header = md_text[:header_end+2] if header_end > 0 else ""
            md_text = header + md_text[header_end+2:4000 - len(header) - 20] + "...<сообщение обрезано>"
        # Попытка отправки с Markdown
        data = {"chat_id": user_id, "text": md_text, "parse_mode": "Markdown"}
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки Markdown: {e}")
        # Фоллбэк без форматирования
        try:
            response = requests.post(url, json={"chat_id": user_id, "text": md_text})
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Фоллбэк plain text не удался: {e}")
            return False

    async def group_messages_by_channel(self, messages):
        """Группировка сообщений по каналам."""
        messages_by_channel = {}
        for msg in messages:
            channel_id = msg.get('channel_id')
            if not channel_id:
                continue
                
            if channel_id not in messages_by_channel:
                messages_by_channel[channel_id] = []
                
            messages_by_channel[channel_id].append(msg)
            
        return messages_by_channel

    async def load_channel_message_pair(self, channel_id, message_id):
        """Загрузка пары канал-сообщение для прямой пересылки."""
        try:
            channel = await self.client.get_entity(int(channel_id))
            message = await self.client.get_messages(channel, ids=int(message_id))
            if message:
                return channel, message
        except Exception as e:
            logger.error(f"Ошибка загрузки сообщения {message_id} из канала {channel_id}: {e}")
            
        return None, None

    async def create_clickable_header(self, msg):
        """Создает кликабельный заголовок сообщения с названием канала и ссылкой на оригинал."""
        try:
            channel_name = msg.get('channel_name', 'Канал')
            channel_id = msg.get('channel_id')
            message_id = msg.get('id')
            
            if not (channel_id and message_id):
                logger.warning(f"Не удалось создать заголовок: отсутствует channel_id или id сообщения")
                return ""
            # Для публичных каналов убираем префикс в URL
            channel_id_clean = str(channel_id)[4:] if str(channel_id).startswith('-100') else channel_id
            message_url = f"https://t.me/c/{channel_id_clean}/{message_id}"
            # Markdown-заголовок
            header = f"[{channel_name}]({message_url})\n\n"
            return header
        except Exception as e:
            logger.error(f"Ошибка при создании заголовка: {e}")
            return ""

    async def send_messages(self):
        """Пересылает уникальные сообщения с добавлением кликабельного заголовка."""
        messages = self.load_unique_messages()
        if not messages:
            logger.warning("Нет уникальных сообщений для отправки")
            return False
        logger.info(f"Пересылаем {len(messages)} сообщений...")

        # Инициализация клиента Telegram и media_handler (для прямого форварда и загрузки медиа)
        target_user = None
        client_ok = await self.initialize_client()
        if not client_ok:
            logger.error("Не удалось инициализировать клиент Telegram.")
        # Если включён прямой форвард и клиент инициализирован, получаем пользователя
        if self.direct_forward and client_ok:
            try:
                target_user = await self.client.get_entity(int(self.user_id))
                logger.info(f"Получен пользователь для форварда: {target_user.id}")
            except Exception as e:
                logger.error(f"Не удалось получить entity пользователя: {e}")
                target_user = None
        elif self.direct_forward and not client_ok:
            self.direct_forward = False

        sent_count = 0
        for msg in messages:
            try:
                # Создаем заголовок для сообщения
                header = await self.create_clickable_header(msg)
                
                # 1. Прямая пересылка оригинала
                if self.direct_forward and target_user:
                    channel, tele_msg = await self.load_channel_message_pair(msg['channel_id'], msg['id'])
                    if channel and tele_msg:
                        # Для прямой пересылки нельзя изменить сообщение, поэтому отправляем заголовок отдельно
                        if header:
                            try:
                                await self.client.send_message(target_user, header, parse_mode='html')
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.error(f"Ошибка отправки заголовка: {e}")
                                await self.client.send_message(target_user, header.replace('<', '').replace('>', ''))
                                await asyncio.sleep(0.5)
                        await self.client.forward_messages(target_user, tele_msg)
                        sent_count += 1
                        logger.info(f"Прямой форвард {msg['id']} с заголовком")
                        await asyncio.sleep(self.wait_delay)
                        continue

                # 2. Пересылка медиа через Bot API
                if msg.get('has_media') and self.media_handler:
                    # загружаем оригинальное сообщение для скачивания медиа
                    channel_entity, tele_msg = await self.load_channel_message_pair(msg['channel_id'], msg['id'])
                    if tele_msg:
                        media_info = await self.media_handler.download_message_media(tele_msg, msg['channel_id'])
                        if media_info:
                            media_info['caption'] = header + media_info.get('caption', '')
                            ok = await self.media_handler.forward_message_with_media(
                                self.bot_token, self.user_id, msg, media_info, msg.get('channel_name')
                            )
                            if ok:
                                sent_count += 1
                                logger.info(f"Bot API форвард медиа {msg['id']} с заголовком")
                                await asyncio.sleep(self.wait_delay)
                                continue

                # 3. Пересылка текста через Bot API
                text = msg.get('message', '').strip()
                if text:
                    # Добавляем заголовок к тексту сообщения
                    text_with_header = header + text
                    if await self.send_message_via_bot(self.user_id, text_with_header):
                        sent_count += 1
                        logger.info(f"Bot API отправка текста {msg['id']} с заголовком")
                    else:
                        logger.error(f"Не удалось отправить текст {msg['id']}")
                await asyncio.sleep(self.wait_delay)
            except Exception as e:
                logger.error(f"Ошибка при обработке сообщения {msg.get('id')}: {e}")

        logger.info(f"Отправлено {sent_count}/{len(messages)} сообщений")
        return sent_count > 0

    async def close(self):
        """Закрытие клиента."""
        if self.client:
            await self.client.disconnect()
            logger.info("Клиент отключен")