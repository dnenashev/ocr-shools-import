#!/usr/bin/env python3
"""
Скрипт для проверки подключения к MongoDB
"""
import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from backend.config import get_settings

settings = get_settings()

async def test_connection():
    """Тестирование подключения к MongoDB"""
    print("=" * 60)
    print("🔍 Тестирование подключения к MongoDB")
    print("=" * 60)
    
    mongo_uri = settings.mongodb_uri
    db_name = settings.mongodb_db_name
    
    # Маскируем пароль в выводе
    safe_uri = mongo_uri
    if "@" in mongo_uri:
        parts = mongo_uri.split("@")
        if "://" in parts[0]:
            protocol_user = parts[0].split("://")
            if len(protocol_user) == 2:
                user_pass = protocol_user[1].split(":")
                if len(user_pass) == 2:
                    safe_uri = f"{protocol_user[0]}://{user_pass[0]}:****@{parts[1]}"
    
    print(f"\n📋 Параметры подключения:")
    print(f"   URI: {safe_uri}")
    print(f"   Database: {db_name}")
    print(f"   Type: {'Atlas (mongodb+srv://)' if 'mongodb+srv://' in mongo_uri else 'Standalone (mongodb://)'}")
    
    try:
        print(f"\n🔌 Подключение...")
        client = AsyncIOMotorClient(
            mongo_uri,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=30000,
        )
        
        # Проверка подключения
        print(f"   Проверка ping...")
        result = await client.admin.command('ping')
        print(f"   ✅ Ping успешен: {result}")
        
        # Проверка доступа к базе
        print(f"\n📊 Проверка базы данных '{db_name}'...")
        db = client[db_name]
        collections = await db.list_collection_names()
        print(f"   ✅ База данных доступна")
        print(f"   Коллекции: {collections if collections else '(пусто)'}")
        
        # Проверка коллекции students
        students_count = await db.students.count_documents({})
        print(f"   📝 Записей в students: {students_count}")
        
        print(f"\n✅ Подключение к MongoDB работает корректно!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Ошибка подключения:")
        print(f"   {error_msg}")
        
        # Полезные советы
        if "SSL" in error_msg or "TLS" in error_msg:
            print(f"\n💡 Решение проблем с SSL:")
            print(f"   1. Убедитесь что строка начинается с mongodb+srv://")
            print(f"   2. Проверьте что в MongoDB Atlas разрешён доступ с вашего IP")
            print(f"   3. Попробуйте добавить в конец URI: ?tlsAllowInvalidCertificates=true")
            print(f"      (только для тестирования, небезопасно для production)")
        elif "authentication" in error_msg.lower():
            print(f"\n💡 Решение проблем с аутентификацией:")
            print(f"   1. Проверьте username и password в URI")
            print(f"   2. Убедитесь что пользователь существует в MongoDB Atlas")
            print(f"   3. Специальные символы в пароле должны быть URL-encoded")
            print(f"      (@ = %40, : = %3A, / = %2F, # = %23, ? = %3F)")
        
        return False
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    try:
        result = asyncio.run(test_connection())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)

