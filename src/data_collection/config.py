"""
Конфигурационный файл для хранения настроек
"""
import json
import os
from typing import Dict, Union

CONFIG_FILE = "config.json"

def save_config(api_id: Union[str, int], api_hash: str) -> None:
    """
    Сохранение конфигурации в файл.
    API ID должен быть целым числом, API Hash - строкой без кавычек.
    """
    # Преобразуем api_id в целое число
    api_id = int(str(api_id).strip())
    # Убираем кавычки из api_hash если они есть
    api_hash = str(api_hash).strip().strip("'").strip('"')
    
    config = {
        'api_id': api_id,
        'api_hash': api_hash
    }
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

def load_config() -> Dict[str, Union[int, str]]:
    """
    Загрузка конфигурации из файла.
    Возвращает словарь с api_id (int) и api_hash (str).
    """
    if not os.path.exists(CONFIG_FILE):
        return {}
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Убеждаемся, что api_id - целое число
            if 'api_id' in config:
                config['api_id'] = int(str(config['api_id']).strip())
            # Убеждаемся, что api_hash - строка без кавычек
            if 'api_hash' in config:
                config['api_hash'] = str(config['api_hash']).strip().strip("'").strip('"')
            return config
    except Exception as e:
        print(f"Ошибка при чтении конфигурации: {e}")
        return {} 