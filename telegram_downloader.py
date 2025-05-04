import os
import json
import logging
import asyncio
import sys
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel, Chat, User
import requests

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
        logging.FileHandler("logs/downloader_log.txt", mode='w', encoding='utf-8'),
        EmojiSafeStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('TelegramDownloader')

# Ensure logs directory exists
if not os.path.exists("logs"):
    os.makedirs("logs")

class TelegramDownloader:
    def __init__(self, config_path='config.json'):
        """Инициализация загрузчика Telegram."""
        self.config = self._load_config(config_path)
        self.last_run_file = os.path.join(self.config['paths']['data_dir'], 'last_run.json')
        self.client = None
        self.session_file = os.path.join(
            self.config['paths']['sessions_dir'], 
            f'tg_session_v3_{self.config["telegram"]["phone"]}'
        )
        self.request_delay = self.config.get('app', {}).get('request_delay', 0.5)
        self.media_enabled = self.config.get('app', {}).get('media_enabled', True)
        self.direct_forward = self.config.get('app', {}).get('direct_forward', True)
        self._ensure_dirs_exist()

    def _load_config(self, config_path):
        """Загрузка конфигурации из JSON файла."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            logger.critical(f"Ошибка загрузки конфигурации: {e}")
            raise

    def _ensure_dirs_exist(self):
        """Создание необходимых директорий."""
        dirs = [
            self.config['paths']['data_dir'],
            self.config['paths']['sessions_dir'],
            self.config['paths']['log_dir'],
            self.config['paths']['reports_dir']
        ]
        for dir_path in dirs:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                logger.info(f"Создана директория: {dir_path}")

    def _get_last_run_time(self):
        """Получение времени последнего запуска парсера с ограничением в 24 часа."""
        max_lookback = datetime.now() - timedelta(hours=24)  # Максимальный период - 24 часа назад
        
        if os.path.exists(self.last_run_file):
            try:
                with open(self.last_run_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    last_run = datetime.fromisoformat(data.get('last_run', ''))
                    # Возвращаем более позднее время: либо время последнего запуска, либо 24 часа назад
                    return max(last_run, max_lookback)
            except Exception as e:
                logger.error(f"Ошибка чтения времени последнего запуска: {e}")
        
        # Если файла нет или произошла ошибка, возвращаем время 24 часа назад
        return max_lookback

    def _save_last_run_time(self):
        """Сохранение времени текущего запуска."""
        try:
            with open(self.last_run_file, 'w', encoding='utf-8') as f:
                json.dump({'last_run': datetime.now().isoformat()}, f)
            logger.info(f"Время запуска сохранено: {datetime.now().isoformat()}")
        except Exception as e:
            logger.error(f"Ошибка сохранения времени запуска: {e}")

    async def initialize_client(self):
        """Инициализация и авторизация клиента Telegram."""
        logger.info("Инициализация клиента Telegram...")
        self.client = TelegramClient(
            self.session_file, 
            self.config['telegram']['api_id'], 
            self.config['telegram']['api_hash'],
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
            await self.client.start(phone=self.config['telegram']['phone'])
            if not await self.client.is_user_authorized():
                logger.info("Необходима авторизация!")
                await self.client.send_code_request(self.config['telegram']['phone'])
                code = input('Введите код подтверждения: ')
                
                # Проверка, требуется ли двухфакторная аутентификация
                try:
                    await self.client.sign_in(self.config['telegram']['phone'], code)
                except SessionPasswordNeededError:
                    password = input('Введите пароль двухфакторной аутентификации: ')
                    await self.client.sign_in(password=password)
            
            logger.info("Авторизация успешна!")
            return True
        except Exception as e:
            logger.error(f"Ошибка при авторизации: {e}")
            return False

    async def get_channels(self):
        """Получение объектов каналов по их ID."""
        channels = []
        for channel_id in self.config['channels']:
            try:
                channel = await self.client.get_entity(int(channel_id))
                # Проверяем тип объекта
                if isinstance(channel, User):
                    channel_title = f"Пользователь {channel.first_name} {channel.last_name or ''}".strip()
                    logger.info(f"Добавлен пользователь: {channel_title} (ID: {channel.id})")
                else:
                    channel_title = getattr(channel, 'title', f'Чат {channel.id}')
                    logger.info(f"Добавлен канал: {channel_title} (ID: {channel.id})")
                
                # Добавляем атрибут title, если его нет
                if not hasattr(channel, 'title'):
                    channel.title = channel_title
                
                channels.append(channel)
            except Exception as e:
                logger.error(f"Ошибка получения канала {channel_id}: {e}")
        return channels

    async def fetch_messages_from_channel(self, channel, last_run_time):
        """Получение новых сообщений из канала с момента последнего запуска."""
        channel_dir = os.path.join(self.config['paths']['data_dir'], str(channel.id))
        if not os.path.exists(channel_dir):
            os.makedirs(channel_dir)
        
        # Используем безопасный способ получения названия канала
        channel_title = getattr(channel, 'title', f'Чат {channel.id}')
        logger.info(f"Получение сообщений из канала '{channel_title}' с {last_run_time.isoformat()}")
        
        messages = []
        try:
            # Получаем сообщения с ограничением в 100 за раз
            async for message in self.client.iter_messages(
                channel, 
                offset_date=last_run_time,
                reverse=True,  # От старых к новым
                limit=None    # Без ограничения общего количества
            ):
                # Пропускаем сообщения без текста (даже если есть медиа)
                if not message.text:
                    logger.info(f"Пропускаем сообщение {message.id} без текста из канала {channel_title}")
                    continue
                    
                # Для прямой пересылки нам не нужно загружать медиа
                msg_data = {
                    'id': message.id,
                    'channel_id': channel.id,
                    'channel_name': channel_title,
                    'date': message.date.isoformat(),
                    'message': message.text or '',
                    'has_media': message.media is not None
                }
                
                # Сохраняем сообщение в файл
                self._save_message_to_file(channel.id, message.id, msg_data)
                
                # Добавляем в общий список для анализа
                messages.append(msg_data)
                
                # Добавляем небольшую задержку, чтобы избежать ограничений API
                await asyncio.sleep(self.request_delay)
                
        except Exception as e:
            logger.error(f"Ошибка при получении сообщений из канала {channel_title}: {e}")
        
        logger.info(f"Получено {len(messages)} сообщений из канала '{channel_title}'")
        return messages

    def _save_message_to_file(self, channel_id, message_id, message_data):
        """Сохранение сообщения в JSON файл."""
        channel_dir = os.path.join(self.config['paths']['data_dir'], str(channel_id))
        filename = f"message_{channel_id}_{message_id}.json"
        filepath = os.path.join(channel_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(message_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения сообщения {message_id} из канала {channel_id}: {e}")

    async def download_messages(self):
        """Основная функция загрузки сообщений."""
        try:
            # Инициализация клиента
            if not await self.initialize_client():
                logger.critical("Невозможно продолжить без авторизации в Telegram.")
                return None
                
            # Получаем время последнего запуска
            last_run_time = self._get_last_run_time()
            logger.info(f"Последний запуск: {last_run_time.isoformat()}")
            
            # Получаем объекты каналов
            channels = await self.get_channels()
            
            if not channels:
                logger.warning("Не найдено ни одного канала для парсинга.")
                return None
                
            # Получаем сообщения из всех каналов
            all_messages = []
            for channel in channels:
                channel_messages = await self.fetch_messages_from_channel(channel, last_run_time)
                all_messages.extend(channel_messages)
            
            logger.info(f"Всего получено {len(all_messages)} новых сообщений из {len(channels)} каналов")
            
            # Сохраняем время текущего запуска
            self._save_last_run_time()
            
            # Создаем файл со списком всех новых сообщений для анализатора
            messages_file = os.path.join(self.config['paths']['data_dir'], 'new_messages.json')
            try:
                with open(messages_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'timestamp': datetime.now().isoformat(),
                        'messages': all_messages
                    }, f, ensure_ascii=False, indent=2)
                logger.info(f"Список новых сообщений сохранен в {messages_file}")
            except Exception as e:
                logger.error(f"Ошибка сохранения списка новых сообщений: {e}")
            
            return all_messages if all_messages else None
            
        except Exception as e:
            logger.critical(f"Критическая ошибка при загрузке сообщений: {e}", exc_info=True)
            return None
        finally:
            # Закрываем клиент в любом случае
            if self.client:
                await self.client.disconnect()
                logger.info("Клиент Telegram отключен.")