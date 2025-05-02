import os
import logging
import asyncio
from datetime import datetime
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
import requests
import re

# Настройка логирования
logger = logging.getLogger('MediaHandler')

class MediaHandler:
    """Класс для обработки медиа-вложений сообщений из Telegram."""
    
    def __init__(self, client, config):
        """
        Инициализация обработчика медиа.
        
        Args:
            client: Инициализированный TelegramClient
            config: Конфигурация приложения
        """
        self.client = client
        self.config = config
        self.data_dir = config['paths']['data_dir']
        self.request_delay = config.get('app', {}).get('request_delay', 0.5)
        
    async def download_message_media(self, message, channel_id):
        """
        Загрузка медиа-файлов из сообщения.
        
        Args:
            message: Объект сообщения Telegram
            channel_id: ID канала
            
        Returns:
            dict: Информация о загруженных медиа-файлах или None
        """
        if not message.media:
            return None
            
        media_info = {
            'type': None,
            'local_path': None,
            'filename': None,
            'mime_type': None,
            'thumbnail_path': None
        }
        
        # Создаем директорию для медиа если не существует
        channel_media_dir = os.path.join(self.data_dir, str(channel_id), 'media')
        os.makedirs(channel_media_dir, exist_ok=True)
        
        try:
            # Генерируем имя файла с датой и ID сообщения для уникальности
            date_str = datetime.now().strftime('%Y%m%d%H%M%S')
            base_filename = f"{date_str}_{message.id}"
            
            # Обрабатываем фото
            if isinstance(message.media, MessageMediaPhoto):
                media_info['type'] = 'photo'
                filename = f"{base_filename}.jpg"
                local_path = os.path.join(channel_media_dir, filename)
                
                # Загружаем фото
                await message.download_media(local_path)
                media_info['local_path'] = local_path
                media_info['filename'] = filename
                media_info['mime_type'] = 'image/jpeg'
                
                logger.info(f"Загружено фото из сообщения {message.id} канала {channel_id}")
                
            # Обрабатываем документы (включая GIF, видео и т.д.)
            elif isinstance(message.media, MessageMediaDocument):
                document = message.media.document
                
                # Определяем тип документа по атрибутам
                for attribute in document.attributes:
                    if hasattr(attribute, 'file_name') and attribute.file_name:
                        original_filename = attribute.file_name
                        extension = os.path.splitext(original_filename)[1]
                        filename = f"{base_filename}{extension}"
                        break
                else:
                    # Если имя файла не определено, используем mime-тип
                    mime_type = document.mime_type
                    if 'image' in mime_type:
                        extension = '.jpg' if 'jpeg' in mime_type else '.png'
                    elif 'video' in mime_type:
                        extension = '.mp4'
                    elif 'gif' in mime_type:
                        extension = '.gif'
                    elif 'audio' in mime_type:
                        extension = '.mp3' if 'mpeg' in mime_type else '.ogg'
                    else:
                        extension = '.bin'  # Неизвестный тип
                    
                    filename = f"{base_filename}{extension}"
                
                local_path = os.path.join(channel_media_dir, filename)
                
                # Загружаем документ
                await message.download_media(local_path)
                
                media_info['type'] = 'document'
                media_info['local_path'] = local_path
                media_info['filename'] = filename
                media_info['mime_type'] = document.mime_type
                
                logger.info(f"Загружен документ из сообщения {message.id} канала {channel_id}")
                
            # Обрабатываем веб-страницы с изображениями
            elif isinstance(message.media, MessageMediaWebPage) and hasattr(message.media.webpage, 'photo'):
                media_info['type'] = 'webpage_photo'
                filename = f"{base_filename}_webpage.jpg"
                local_path = os.path.join(channel_media_dir, filename)
                
                # Загружаем фото из веб-страницы
                await message.download_media(local_path)
                media_info['local_path'] = local_path
                media_info['filename'] = filename
                media_info['mime_type'] = 'image/jpeg'
                
                logger.info(f"Загружено фото из веб-страницы, сообщение {message.id} канала {channel_id}")
            
            else:
                logger.info(f"Неподдерживаемый тип медиа в сообщении {message.id} канала {channel_id}")
                return None
                
            # Добавляем задержку после загрузки медиа
            await asyncio.sleep(self.request_delay)
                
            return media_info
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке медиа из сообщения {message.id} канала {channel_id}: {e}")
            return None

    async def forward_media_to_bot(self, bot_token, chat_id, media_info, caption=None):
        """
        Пересылка медиа-файла в бот.
        
        Args:
            bot_token: Токен бота Telegram
            chat_id: ID чата/пользователя для отправки
            media_info: Информация о медиа-файле
            caption: Подпись к медиа (опционально)
            
        Returns:
            bool: True если отправка успешна, иначе False
        """
        if not media_info or not media_info.get('local_path'):
            return False
            
        try:
            local_path = media_info['local_path']
            media_type = media_info.get('type', 'document')
            
            # Проверяем, что файл существует
            if not os.path.exists(local_path):
                logger.error(f"Файл {local_path} не найден")
                return False
                
            # Определяем метод API в зависимости от типа файла
            if media_type == 'photo' or media_type == 'webpage_photo':
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                method = 'photo'
            elif 'video' in media_info.get('mime_type', ''):
                url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
                method = 'video'
            elif 'audio' in media_info.get('mime_type', ''):
                url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
                method = 'audio'
            elif 'gif' in media_info.get('mime_type', '') or media_info.get('filename', '').endswith('.gif'):
                url = f"https://api.telegram.org/bot{bot_token}/sendAnimation"
                method = 'animation'
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
                method = 'document'
                
            # Подготавливаем данные для запроса
            data = {
                'chat_id': chat_id,
                'parse_mode': 'HTML'
            }
            
            if caption:
                # Преобразуем Markdown в HTML
                caption = self._convert_markdown_to_html(caption)
                
                # Ограничение длины описания для Telegram API - 1024 символа
                if len(caption) > 1024:
                    data['caption'] = caption[:1021] + "..."
                else:
                    data['caption'] = caption
                
            files = {
                method: (media_info.get('filename', os.path.basename(local_path)), open(local_path, 'rb'))
            }
            
            # Отправляем запрос
            try:
                response = requests.post(url, data=data, files=files)
                response.raise_for_status()
            except Exception as e:
                if "can't parse entities" in str(e):
                    logger.warning(f"Ошибка парсинга HTML, отправляем без форматирования")
                    # Если возникла ошибка парсинга HTML, пробуем отправить без форматирования
                    data['parse_mode'] = None
                    response = requests.post(url, data=data, files=files)
                    response.raise_for_status()
                else:
                    raise
            
            logger.info(f"Медиа-файл {media_info.get('filename')} успешно отправлен в бот")
            
            # Добавляем задержку после отправки
            await asyncio.sleep(self.request_delay)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке медиа в бот: {e}")
            return False
        finally:
            # Закрываем файл если он был открыт
            if 'files' in locals() and method in files:
                files[method][1].close()

    def _convert_markdown_to_html(self, text):
        """Конвертирует Markdown-форматирование в HTML."""
        # Замена жирного текста: **text** или __text__ -> <b>text</b>
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
        
        # Замена курсива: *text* или _text_ -> <i>text</i>
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
        text = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<i>\1</i>', text)
        
        # Замена моноширинного текста: `text` -> <code>text</code>
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        
        # Преобразование ссылок: [text](url) -> <a href="url">text</a>
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
        
        return text

    async def forward_message_with_media(self, bot_token, chat_id, message, media_info, channel_name=None):
        """
        Пересылка сообщения с медиа в бот.
        
        Args:
            bot_token: Токен бота Telegram
            chat_id: ID чата/пользователя
            message: Данные сообщения (словарь с текстом и метаданными)
            media_info: Информация о медиа
            channel_name: Название канала (опционально)
        
        Returns:
            bool: True если отправка успешна
        """
        if not media_info:
            return False
            
        try:
            # Используем существующий caption, если он передан через media_info
            # (это может быть заголовок, добавленный в message_sender.py)
            caption = media_info.get('caption', '')
            
            # Получаем текст сообщения
            msg_text = message.get('message', '')
            
            # Если caption не был передан, формируем его с нуля
            if not caption:
                # Формируем подпись с указанием источника
                source_info = f"*Источник: {channel_name}*" if channel_name else ""
                date_info = f"*Дата: {message.get('date', '')}*" if message.get('date') else ""
                
                # Добавляем текст и метаданные
                caption = f"{msg_text}\n\n{date_info}\n{source_info}".strip()
            # Если caption уже содержит заголовок, но не текст сообщения, добавляем его
            elif msg_text and msg_text not in caption:
                caption += msg_text
            
            # Ограничиваем длину текста для подписи (максимум 1024 символа для подписи)
            if len(caption) > 1024:
                caption = caption[:1021] + "..."
                
            # Отправляем медиа с подписью
            result = await self.forward_media_to_bot(bot_token, chat_id, media_info, caption)
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения с медиа: {e}")
            return False 