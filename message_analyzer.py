import os
import json
import logging
import sys
import re
import requests
from datetime import datetime
import asyncio
import time
import difflib

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
        logging.FileHandler("logs/analyzer_log.txt", mode='w', encoding='utf-8'),
        EmojiSafeStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('MessageAnalyzer')

# Ensure logs dir exists
if not os.path.exists("logs"):
    os.makedirs("logs")

class MessageAnalyzer:
    def __init__(self, config_path='config.json'):
        """Инициализация анализатора сообщений."""
        self.config = self._load_config(config_path)
        self.data_dir = self.config['paths']['data_dir']
        self.llm_enabled = self.config.get('llm', {}).get('enabled', False)
        self.llm_api_url = self.config.get('llm', {}).get('lm_studio_api_url', '')
        self.llm_model = self.config.get('llm', {}).get('lm_studio_model', 'saiga_yandexgpt_8b_gguf')
        
    def _load_config(self, config_path):
        """Загрузка конфигурации из JSON файла."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            logger.critical(f"Ошибка загрузки конфигурации: {e}")
            raise

    def load_messages(self):
        """Загрузка списка новых сообщений для анализа."""
        messages_file = os.path.join(self.data_dir, 'new_messages.json')
        
        if not os.path.exists(messages_file):
            logger.warning(f"Файл с новыми сообщениями не найден: {messages_file}")
            return None
            
        try:
            with open(messages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                messages = data.get('messages', [])
                timestamp = data.get('timestamp', '')
                
            logger.info(f"Загружено {len(messages)} сообщений от {timestamp}")
            return messages
        except Exception as e:
            logger.error(f"Ошибка загрузки сообщений для анализа: {e}")
            return None
            
    def _call_llm_api(self, prompt):
        """Вызов API языковой модели."""
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": "Ты - помощник, который анализирует сообщения из телеграм-каналов и определяет, какие из них уникальны и содержат наиболее полную информацию. Твоя задача - выделить сообщения, которые не дублируют друг друга по информационному содержанию, даже если они из разных каналов."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4
        }
        
        try:
            response = requests.post(self.llm_api_url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка запроса к LLM API: {e}")
            return {"choices": [{"message": {"content": "[]"}}]}

    def _normalize_text(self, text: str) -> str:
        """Нормализует текст для более корректного сравнения."""
        # Приводим к нижнему регистру
        text = text.lower()
        # Удаляем ссылки
        text = re.sub(r"http[s]?://\S+", "", text)
        # Удаляем символы пунктуации, спец‐символы, эмодзи
        text = re.sub(r"[^\w\s]", "", text)
        # Сжимаем множественные пробелы
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _remove_near_duplicates(self, messages, threshold: float = 0.9):
        """Удаляет сообщения, очень похожие по содержанию (почти дубликаты).

        Оставляет наиболее длинный вариант текста среди схожих.
        threshold – минимальная доля схожести (0..1), выше – строже.
        """
        if not messages:
            return []

        unique_messages = []
        normalized_texts = []

        for msg in messages:
            norm = self._normalize_text(msg.get("message", ""))
            is_duplicate = False
            for i, saved_norm in enumerate(normalized_texts):
                # Используем SequenceMatcher для оценки схожести
                if difflib.SequenceMatcher(None, norm, saved_norm).ratio() >= threshold:
                    is_duplicate = True
                    # Оставляем более длинный текст как более информативный
                    if len(norm) > len(saved_norm):
                        unique_messages[i] = msg
                        normalized_texts[i] = norm
                    break
            if not is_duplicate:
                unique_messages.append(msg)
                normalized_texts.append(norm)

        removed_cnt = len(messages) - len(unique_messages)
        if removed_cnt:
            logger.info(f"Удалено {removed_cnt} дублирующих сообщений перед анализом")
        return unique_messages

    def analyze_messages(self, messages):
        """Анализ сообщений для выявления уникальных."""
        if not messages:
            logger.info("Нет сообщений для анализа")
            return []
            
        logger.info(f"Анализ {len(messages)} сообщений для определения уникальных...")
        
        # Удаляем явные дубликаты до передачи в LLM
        messages = self._remove_near_duplicates(messages)
        
        # Проверяем настройки LLM
        if not self.llm_enabled:
            logger.warning("LLM отключен в конфигурации, анализ не будет выполнен")
            return messages  # Возвращаем все сообщения, если LLM отключен
            
        # Если всего одно сообщение, оно уникально по определению
        if len(messages) <= 1:
            return messages
            
        # Создаем список текстов сообщений
        message_texts = []
        for i, msg in enumerate(messages):
            message_idx = i + 1  # Индекс сообщения в списке, начиная с 1
            message_texts.append(
                f"Сообщение #{message_idx} (Канал: {msg['channel_name']}):\n{msg['message']}"
            )
        
        # Обработка партиями сообщений
        max_context_items = 30  # Максимальное количество сообщений для одного запроса
        unique_messages = []
        
        for i in range(0, len(messages), max_context_items):
            batch_size = min(max_context_items, len(messages) - i)
            batch_messages = messages[i:i + batch_size]
            batch_texts = message_texts[i:i + batch_size]
            batch_indices = list(range(i + 1, i + batch_size + 1))  # Индексы этой партии
            
            messages_context = "\n\n".join(batch_texts)
            
            prompt = f"""Проанализируй следующие сообщения из разных телеграм-каналов и определи, какие из них содержат уникальную информацию:

{messages_context}

ВАЖНО: Если, выбирая уникальные сообщения ты обранужишь несколько сообщений которые относятся к одной и той же новости или событию(даже если они из разных каналов), выбери ТОЛЬКО ОДНО - лучшее, самое полное и информативное, остальные игнорируй. 

ОЧЕНЬ ВАЖНО: Для каждого сообщения, которое ты считаешь уникальным, напиши только его номер (например, #1, #2) в виде массива чисел: [1, 2, 5, 8]
Не используй в ответе никакие другие идентификаторы, только номера сообщений как они указаны в начале каждого сообщения.
Возвращай только числа без символа "#".

Твой ответ должен содержать только JSON-массив чисел и ничего больше.
Например: [1, 3, 5, 7]
"""

            # Запрос к LLM API
            response = self._call_llm_api(prompt)
            
            # Обработка ответа
            try:
                # Извлекаем массив из ответа
                response_text = response.get('choices', [{}])[0].get('message', {}).get('content', '')
                
                # Находим JSON в ответе - любой массив чисел в квадратных скобках
                match = re.search(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', response_text)
                
                if match:
                    json_str = match.group(0)
                    unique_indices = json.loads(json_str)
                    
                    # Находим уникальные сообщения по индексу в этой партии
                    for idx in unique_indices:
                        # Проверяем, что индекс в пределах текущей партии
                        if idx in batch_indices:
                            # Получаем индекс в исходном списке
                            original_idx = idx - 1  # -1 потому что индексы начинаются с 1
                            if 0 <= original_idx < len(messages):
                                unique_msg = messages[original_idx]
                                unique_messages.append(unique_msg)
                                logger.info(f"Сообщение #{idx} (ID: {unique_msg['id']}) из канала {unique_msg['channel_name']} определено как уникальное")
                else:
                    logger.warning(f"Не удалось извлечь массив индексов из ответа LLM: {response_text}")
                    # Если не удалось распарсить ответ, берем все сообщения текущей партии
                    unique_messages.extend(batch_messages)
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке ответа LLM: {e}")
                # При ошибке берем все сообщения в этой партии
                unique_messages.extend(batch_messages)
        
        logger.info(f"Анализ завершен. Определено {len(unique_messages)} уникальных сообщений из {len(messages)}")
        
        # Сохраняем уникальные сообщения в файл
        self._save_unique_messages(unique_messages)
        
        return unique_messages

    def _save_unique_messages(self, unique_messages):
        """Сохранение списка уникальных сообщений."""
        if not unique_messages:
            return
            
        output_file = os.path.join(self.data_dir, 'unique_messages.json')
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'messages': unique_messages
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"Уникальные сообщения сохранены в {output_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения уникальных сообщений: {e}")

    def filter_informative_messages(self, messages):
        """Фильтрует сообщения, оставляя только информативные и полезные."""
        if not messages:
            logger.info("Нет сообщений для фильтрации")
            return []
        
        logger.info(f"Фильтрация {len(messages)} сообщений для определения информативных...")
        
        if not self.llm_enabled:
            logger.warning("LLM отключен в конфигурации, фильтрация не будет выполнена")
            return messages

        # Обработка сообщений партиями
        max_context_items = 30  # Максимальное количество сообщений в одном запросе
        informative_messages = []
        
        for i in range(0, len(messages), max_context_items):
            batch_size = min(max_context_items, len(messages) - i)
            batch_messages = messages[i:i + batch_size]
            
            # Формируем контекст для LLM
            message_texts = []
            for j, msg in enumerate(batch_messages):
                message_idx = j + 1  # Индекс сообщения в текущей партии, начиная с 1
                message_texts.append(
                    f"Сообщение #{message_idx} (Канал: {msg['channel_name']}):\n{msg['message']}"
                )
            
            messages_context = "\n\n".join(message_texts)
            
            prompt = f"""Проанализируй следующие сообщения из телеграм-каналов и определи, какие из них содержат полезную информацию(информативные):

{messages_context}

Критерии информативного сообщения:
1. Содержит достаточно контекста для понимания
2. Не является спапом или эмоциональным постом без конкретики
3. Не являются объявлением о вакансиях или предложением работы
4. Не являются анонсом или приглашением на мероприятие(конференции, круглые столы, вебинары, семинары, тренинги, курсы)

Для каждого информативного сообщения, напиши только его номер в виде массива чисел: [1, 2, 5, 8]
Твой ответ должен содержать только JSON-массив чисел и ничего больше.
Например: [1, 3, 5, 7]
"""

            # Запрос к LLM API
            response = self._call_llm_api(prompt)
            
            # Обработка ответа
            try:
                # Извлекаем массив из ответа
                response_text = response.get('choices', [{}])[0].get('message', {}).get('content', '')
                
                # Находим JSON в ответе - любой массив чисел в квадратных скобках
                match = re.search(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', response_text)
                
                if match:
                    json_str = match.group(0)
                    informative_indices = json.loads(json_str)
                    
                    # Извлекаем информативные сообщения по индексам
                    for idx in informative_indices:
                        if 1 <= idx <= len(batch_messages):
                            msg = batch_messages[idx - 1]  # -1 потому что индексы начинаются с 1
                            informative_messages.append(msg)
                            logger.info(f"Сообщение #{idx} (ID: {msg['id']}) из канала {msg['channel_name']} помечено как информативное")
                else:
                    logger.warning(f"Не удалось извлечь массив индексов из ответа LLM: {response_text}")
                    # Если не удалось распарсить ответ, берем все сообщения текущей партии
                    informative_messages.extend(batch_messages)
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке ответа LLM: {e}")
                # При ошибке берем все сообщения в этой партии
                informative_messages.extend(batch_messages)
            
            # Добавляем задержку между запросами
            time.sleep(self.request_delay if hasattr(self, 'request_delay') else 0.5)
        
        logger.info(f"Фильтрация завершена. Определено {len(informative_messages)} информативных сообщений из {len(messages)}")
        
        # Сохраняем информативные сообщения в файл
        output_file = os.path.join(self.data_dir, 'informative_messages.json')
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'messages': informative_messages
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"Информативные сообщения сохранены в {output_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения информативных сообщений: {e}")
        
        return informative_messages