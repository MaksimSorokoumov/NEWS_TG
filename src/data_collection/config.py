"""
Конфигурационный файл для хранения настроек
"""
import json
import os
from typing import Dict

CONFIG_FILE = "config.json"

def save_config(api_id: str, api_hash: str) -> None:
    """Сохранение конфигурации в файл"""
    config = {
        'api_id': api_id,
        'api_hash': api_hash
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

def load_config() -> Dict[str, str]:
    """Загрузка конфигурации из файла"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {} 