from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from backend.config import get_settings

settings = get_settings()


class MongoDB:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db = MongoDB()


async def connect_to_mongo():
    """Подключение к MongoDB"""
    try:
        mongo_uri = settings.mongodb_uri
        
        # Для MongoDB Atlas (mongodb+srv://) SSL включен по умолчанию
        # Если возникают проблемы с SSL, можно добавить параметры в URI:
        # ?tls=true&tlsAllowInvalidCertificates=false
        
        print(f"🔌 Connecting to MongoDB...")
        print(f"   Database: {settings.mongodb_db_name}")
        print(f"   URI format: {'mongodb+srv://' if 'mongodb+srv://' in mongo_uri else 'mongodb://'}...")
        
        # Для MongoDB Atlas добавляем параметры если их нет
        # Если в URI нет параметров, добавляем стандартные для Atlas
        if "mongodb+srv://" in mongo_uri:
            if "?" not in mongo_uri:
                # Добавляем параметры для Atlas
                mongo_uri = f"{mongo_uri}?retryWrites=true&w=majority"
            elif "retryWrites" not in mongo_uri:
                # Добавляем retryWrites если его нет
                separator = "&" if "?" in mongo_uri else "?"
                mongo_uri = f"{mongo_uri}{separator}retryWrites=true&w=majority"
        
        # Создаём клиент с правильными настройками для Atlas
        db.client = AsyncIOMotorClient(
            mongo_uri,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=30000,
            # Для Atlas SSL включен по умолчанию через mongodb+srv://
            # Если проблемы с SSL, можно добавить tlsAllowInvalidCertificates=true в URI
        )
        
        # Проверяем подключение
        await db.client.admin.command('ping')
        
        db.db = db.client[settings.mongodb_db_name]
        
        # Создаем индексы (если их ещё нет)
        try:
            await db.db.students.create_index("created_at")
            await db.db.students.create_index("sent_to_amo")
        except Exception as idx_error:
            # Индексы могут уже существовать - это нормально
            print(f"   Note: {idx_error}")
        
        print(f"✅ Connected to MongoDB: {settings.mongodb_db_name}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error connecting to MongoDB:")
        print(f"   {error_msg}")
        
        # Полезные советы по исправлению
        if "SSL" in error_msg or "TLS" in error_msg:
            print("\n💡 SSL/TLS ошибка. Проверьте:")
            print("   1. Строка подключения должна начинаться с mongodb+srv://")
            print("   2. В MongoDB Atlas разрешён доступ с вашего IP адреса")
            print("   3. Пароль в URI правильно закодирован (особые символы как @, :, /, #, ? должны быть URL-encoded)")
        elif "authentication" in error_msg.lower():
            print("\n💡 Ошибка аутентификации. Проверьте:")
            print("   1. Правильность username и password в URI")
            print("   2. Пользователь существует в MongoDB Atlas")
        elif "timeout" in error_msg.lower():
            print("\n💡 Таймаут подключения. Проверьте:")
            print("   1. Интернет соединение")
            print("   2. MongoDB Atlas доступен")
            print("   3. Firewall не блокирует подключение")
        
        raise


async def close_mongo_connection():
    """Закрытие соединения с MongoDB"""
    if db.client:
        db.client.close()
        print("MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    """Получение экземпляра базы данных"""
    return db.db


async def get_students_collection():
    """Получение коллекции students"""
    return db.db.students

