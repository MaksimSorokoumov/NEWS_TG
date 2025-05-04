import os
import sys
import asyncio
import logging
from datetime import datetime
import re

# Импортируем классы из модулей
from telegram_downloader import TelegramDownloader
from message_analyzer import MessageAnalyzer
from message_sender import MessageSender

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
        logging.FileHandler("logs/main_log.txt", mode='w', encoding='utf-8'),
        EmojiSafeStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('TelegramParserMain')

# Ensure logs directory exists
if not os.path.exists("logs"):
    os.makedirs("logs")

async def parse_and_send():
    """Основная функция для запуска всего процесса парсинга и отправки."""
    start_time = datetime.now()
    logger.info(f"Запуск процесса парсинга Telegram каналов в {start_time.isoformat()}")
    
    # Шаг 1: Загрузка сообщений из каналов
    logger.info("Шаг 1: Загрузка сообщений из каналов")
    downloader = TelegramDownloader()
    messages = await downloader.download_messages()
    
    if not messages:
        logger.warning("Не найдено новых сообщений для анализа.")
        return
    
    logger.info(f"Загружено {len(messages)} сообщений из каналов.")
    
    # Шаг 2: Анализ сообщений для выявления полезных и информативных
    logger.info("Шаг 2: Фильтрация информативных сообщений")
    analyzer = MessageAnalyzer()
    informative_messages = analyzer.filter_informative_messages(messages)
    
    if not informative_messages:
        logger.warning("Не найдено информативных сообщений после фильтрации.")
        return
    
    logger.info(f"Найдено {len(informative_messages)} информативных сообщений из {len(messages)}")
    
    # Шаг 3: Анализ информативных сообщений для выявления уникальных
    logger.info("Шаг 3: Анализ информативных сообщений для выявления уникальных")
    unique_messages = analyzer.analyze_messages(informative_messages)
    
    if not unique_messages:
        logger.warning("Не найдено уникальных сообщений для отправки.")
        return
    
    logger.info(f"Найдено {len(unique_messages)} уникальных сообщений из {len(informative_messages)} информативных")
    
    # Шаг 4: Отправка уникальных сообщений
    logger.info("Шаг 4: Отправка уникальных сообщений")
    sender = MessageSender()
    success = await sender.send_messages()
    
    if success:
        logger.info("Сообщения успешно отправлены")
    else:
        logger.error("Не удалось отправить сообщения")
    
    # Закрываем клиент отправителя
    await sender.close()
    
    # Выводим статистику
    end_time = datetime.now()
    duration = end_time - start_time
    
    logger.info(f"Процесс парсинга завершен за {duration}")
    logger.info(f"Статистика: загружено {len(messages)} сообщений, найдено {len(informative_messages)} информативных, {len(unique_messages)} уникальных, отправлено: {len(unique_messages) if success else 0}")

async def run_download():
    """Запуск только загрузки сообщений."""
    logger.info("Запуск загрузки сообщений из каналов")
    downloader = TelegramDownloader()
    messages = await downloader.download_messages()
    
    if messages:
        logger.info(f"Загружено {len(messages)} сообщений.")
    else:
        logger.info("Не удалось загрузить сообщения или новых сообщений нет.")

async def run_analyze():
    """Запуск только анализа сообщений."""
    logger.info("Запуск анализа загруженных сообщений")
    analyzer = MessageAnalyzer()
    messages = analyzer.load_messages()
    
    if not messages:
        logger.info("Нет сообщений для анализа")
        return
    
    # Шаг 1: Фильтрация информативных сообщений
    logger.info("Шаг 1: Фильтрация информативных сообщений")
    informative_messages = analyzer.filter_informative_messages(messages)
    
    if not informative_messages:
        logger.warning("Не найдено информативных сообщений после фильтрации.")
        return
    
    logger.info(f"Найдено {len(informative_messages)} информативных сообщений из {len(messages)}")
    
    # Шаг 2: Определение уникальных информативных сообщений
    logger.info("Шаг 2: Определение уникальных информативных сообщений")
    unique_messages = analyzer.find_unique_messages(informative_messages)
    
    if unique_messages:
        logger.info(f"Найдено {len(unique_messages)} уникальных сообщений из {len(informative_messages)} информативных")
    else:
        logger.info("Не найдено уникальных сообщений")

async def run_send():
    """Запуск только отправки сообщений."""
    logger.info("Запуск отправки уникальных сообщений")
    sender = MessageSender()
    success = await sender.send_messages()
    
    if success:
        logger.info("Сообщения успешно отправлены")
    else:
        logger.info("Не удалось отправить сообщения")
        
    await sender.close()

async def main():
    """Обработка аргументов командной строки."""
    if len(sys.argv) < 2:
        # Если аргументов нет, запускаем `run` по умолчанию
        await parse_and_send()
        return
        
    command = sys.argv[1].lower()
    
    if command == "run":
        await parse_and_send()
    elif command == "download":
        await run_download()
    elif command == "analyze":
        await run_analyze()
    elif command == "send":
        await run_send()


if __name__ == "__main__":
    asyncio.run(main()) 
    