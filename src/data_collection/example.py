"""
Пример использования TelegramDataCollector с консольным интерфейсом
"""
import asyncio
import os
from telegram_api import TelegramDataCollector
from config import load_config, save_config

async def display_menu():
    """Отображение меню"""
    print("\n=== Меню ===")
    print("1. Показать последние диалоги")
    print("2. Получить сообщения из диалога")
    print("3. Просмотреть сохранённые сообщения")
    print("4. Выход")
    return input("Выберите действие (1-4): ")

async def main():
    # Пробуем загрузить конфигурацию
    config = load_config()
    api_id = config.get('api_id') or os.getenv('TELEGRAM_API_ID')
    api_hash = config.get('api_hash') or os.getenv('TELEGRAM_API_HASH')
    
    # Если конфигурация не найдена, запрашиваем данные у пользователя
    if not api_id or not api_hash:
        print("API ID и Hash не найдены в конфигурации.")
        print("Вы можете получить их на https://my.telegram.org/apps")
        api_id = input("Введите API ID: ")
        api_hash = input("Введите API Hash: ")
        
        # Спрашиваем, хочет ли пользователь сохранить конфигурацию
        if input("Сохранить эти данные для следующих запусков? (y/n): ").lower() == 'y':
            save_config(api_id, api_hash)
            print("Конфигурация сохранена!")
    
    collector = TelegramDataCollector(api_id=api_id, api_hash=api_hash)
    await collector.start()
    
    try:
        while True:
            choice = await display_menu()
            
            if choice == '1':
                # Показываем диалоги
                dialogs = await collector.get_dialogs(limit=10)
                print("\n=== Последние диалоги ===")
                for dialog in dialogs:
                    print(f"ID: {dialog['id']}")
                    print(f"Название: {dialog['name']}")
                    print(f"Непрочитано: {dialog['unread_count']}")
                    print("---")
                    
            elif choice == '2':
                # Получаем сообщения из диалога
                dialog_id = input("Введите ID диалога: ")
                try:
                    dialog_id = int(dialog_id)
                    limit = int(input("Сколько сообщений получить (по умолчанию 100): ") or "100")
                    
                    print(f"\nПолучаем сообщения из диалога {dialog_id}...")
                    messages = await collector.get_messages(dialog_id, limit=limit)
                    
                    print(f"\nПолучено {len(messages)} сообщений:")
                    for msg in messages:
                        print(f"[{msg['date']}] {msg['text']}")
                except ValueError:
                    print("Ошибка: ID диалога должен быть числом")
                    
            elif choice == '3':
                # Просматриваем сохранённые сообщения
                dialog_id = input("Введите ID диалога (пустое значение для всех диалогов): ")
                try:
                    dialog_id = int(dialog_id) if dialog_id else None
                    messages = collector.get_saved_messages(dialog_id)
                    
                    print(f"\nНайдено {len(messages)} сохранённых сообщений:")
                    for msg in messages:
                        print(f"[{msg['date']}] {msg['text']}")
                except ValueError:
                    print("Ошибка: ID диалога должен быть числом")
                    
            elif choice == '4':
                print("Завершение работы...")
                break
                
            else:
                print("Неверный выбор. Попробуйте снова.")
                
    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем")
    finally:
        await collector.stop()

if __name__ == "__main__":
    asyncio.run(main()) 