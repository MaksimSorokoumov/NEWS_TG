"""
Модуль для получения данных из Telegram с использованием Telethon.
"""
from telethon import TelegramClient
from telethon.tl.types import Message
import logging
import json
import os
from datetime import datetime
from typing import List, Optional

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramDataCollector:
    def __init__(
        self, 
        api_id: str,
        api_hash: str,
        session_name: str = "telegram_session",
        storage_path: str = "data/raw/telegram"
    ):
        """
        Инициализация сборщика данных Telegram.
        
        Args:
            api_id (str): API ID от Telegram
            api_hash (str): API Hash от Telegram
            session_name (str): Имя сессии для сохранения
            storage_path (str): Путь для сохранения собранных данных
        """
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.storage_path = storage_path
        
        # Создаём директорию для хранения данных, если она не существует
        os.makedirs(storage_path, exist_ok=True)
        
    async def start(self):
        """Запуск клиента"""
        await self.client.start()
        logger.info("Клиент Telegram успешно запущен")
        
    async def stop(self):
        """Остановка клиента"""
        await self.client.disconnect()
        logger.info("Клиент Telegram остановлен")
        
    async def get_dialogs(self, limit: int = 10) -> List[dict]:
        """
        Получение списка последних диалогов.
        
        Args:
            limit (int): Максимальное количество диалогов
            
        Returns:
            List[dict]: Список диалогов с основной информацией
        """
        dialogs = []
        async for dialog in self.client.iter_dialogs(limit=limit):
            dialog_info = {
                'id': dialog.id,
                'name': dialog.name,
                'unread_count': dialog.unread_count,
                'is_group': dialog.is_group,
                'is_channel': dialog.is_channel
            }
            dialogs.append(dialog_info)
            
        return dialogs
        
    async def get_messages(
        self, 
        dialog_id: int, 
        limit: int = 100,
        save: bool = True
    ) -> List[dict]:
        """
        Получение сообщений из конкретного диалога.
        
        Args:
            dialog_id (int): ID диалога
            limit (int): Максимальное количество сообщений
            save (bool): Сохранять ли сообщения в файл
            
        Returns:
            List[dict]: Список сообщений
        """
        messages = []
        async for message in self.client.iter_messages(dialog_id, limit=limit):
            if not isinstance(message, Message):
                continue
                
            message_data = {
                'id': message.id,
                'date': message.date.isoformat(),
                'text': message.text,
                'from_id': message.from_id.user_id if message.from_id else None,
                'reply_to_msg_id': message.reply_to_msg_id,
                'forward_from': message.forward.from_id if message.forward else None
            }
            messages.append(message_data)
            
            if save:
                filename = f"{self.storage_path}/messages_{dialog_id}_{datetime.now().strftime('%Y%m%d')}.json"
                try:
                    with open(filename, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(message_data, ensure_ascii=False) + '\n')
                    logger.info(f"Сообщение {message_data['id']} сохранено")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении сообщения: {e}")
                    
        return messages
        
    def get_saved_messages(self, dialog_id: Optional[int] = None) -> List[dict]:
        """
        Чтение сохранённых сообщений из файлов.
        
        Args:
            dialog_id (Optional[int]): ID диалога для фильтрации
            
        Returns:
            List[dict]: Список сохранённых сообщений
        """
        messages = []
        for filename in os.listdir(self.storage_path):
            if not filename.endswith('.json'):
                continue
                
            if dialog_id and not f"messages_{dialog_id}_" in filename:
                continue
                
            filepath = os.path.join(self.storage_path, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        messages.append(json.loads(line.strip()))
            except Exception as e:
                logger.error(f"Ошибка при чтении файла {filename}: {e}")
                
        return messages 