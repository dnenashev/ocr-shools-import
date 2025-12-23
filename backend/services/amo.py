import httpx
from typing import Optional, List, Dict, Any
from backend.config import get_settings
from backend.database.mongodb import get_students_collection
from bson import ObjectId

settings = get_settings()


class AMOCRMService:
    """Сервис для работы с AMO CRM API"""
    
    def __init__(self):
        # Домен берём из AMO_REDIRECT_URI (https://pk1amomabiuru.amocrm.ru -> pk1amomabiuru.amocrm.ru)
        redirect_uri = settings.amo_redirect_uri
        if redirect_uri.startswith("https://"):
            self.domain = redirect_uri.replace("https://", "")
        elif redirect_uri.startswith("http://"):
            self.domain = redirect_uri.replace("http://", "")
        else:
            self.domain = redirect_uri or settings.amo_domain
        
        self.access_token = settings.amo_long_token  # JWT токен
        self.refresh_token = settings.amo_short_key
        self.client_id = settings.integration_id
        self.client_secret = settings.amo_secret_key
        self.base_url = f"https://{self.domain}"
    
    def _get_headers(self) -> dict:
        """Получение заголовков для API запросов"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def refresh_access_token(self) -> bool:
        """Обновление access token через refresh token"""
        url = f"{self.base_url}/oauth2/access_token"
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "redirect_uri": self.base_url
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                # В реальном приложении нужно сохранить токены
                return True
            
            print(f"Failed to refresh token: {response.status_code} - {response.text}")
            return False
    
    async def create_contact(self, fio: str, phone: str, custom_fields: Dict[str, Any] = None) -> Optional[int]:
        """
        Создание контакта в AMO CRM
        Возвращает ID созданного контакта или None при ошибке
        """
        url = f"{self.base_url}/api/v4/contacts"
        
        # Разбиваем ФИО на части
        name_parts = fio.split()
        first_name = name_parts[1] if len(name_parts) > 1 else fio
        last_name = name_parts[0] if len(name_parts) > 0 else ""
        
        contact_data = {
            "name": fio,
            "first_name": first_name,
            "last_name": last_name,
            "custom_fields_values": []
        }
        
        # Добавляем телефон
        if phone:
            contact_data["custom_fields_values"].append({
                "field_code": "PHONE",
                "values": [{"value": phone, "enum_code": "WORK"}]
            })
        
        payload = [contact_data]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                if "_embedded" in data and "contacts" in data["_embedded"]:
                    return data["_embedded"]["contacts"][0]["id"]
            
            # Попробуем обновить токен и повторить
            if response.status_code == 401:
                if await self.refresh_access_token():
                    return await self.create_contact(fio, phone, custom_fields)
            
            print(f"Failed to create contact: {response.status_code} - {response.text}")
            return None
    
    async def create_lead(
        self, 
        name: str, 
        contact_id: int,
        application_type: str = "",
        school: str = "",
        student_class: str = ""
    ) -> Optional[int]:
        """
        Создание сделки (лида) в AMO CRM
        Возвращает ID созданной сделки или None при ошибке
        """
        from datetime import datetime
        
        url = f"{self.base_url}/api/v4/leads"
        
        # Формируем название заявки: тип + дата
        today = datetime.now().strftime("%d.%m.%Y")
        lead_name = f"Заявка {application_type} {today}" if application_type else f"Заявка {today}"
        
        lead_data = {
            "name": lead_name,
            "_embedded": {
                "contacts": [{"id": contact_id}]
            },
            "custom_fields_values": []
        }
        
        # Добавляем тег типа заявки
        if application_type:
            # В AMO API v4 можно добавлять теги по имени или по ID
            # Попробуем получить ID, если не получится - используем имя
            tag_id = await self._get_or_create_tag(application_type)
            if tag_id:
                lead_data["_embedded"]["tags"] = [{"id": tag_id}]
            else:
                # Если ID не получен, добавляем тег по имени (AMO создаст его автоматически)
                lead_data["_embedded"]["tags"] = [{"name": application_type}]
        
        # Можно добавить кастомные поля для школы и класса
        # Для этого нужно знать ID полей в AMO
        
        payload = [lead_data]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                if "_embedded" in data and "leads" in data["_embedded"]:
                    return data["_embedded"]["leads"][0]["id"]
            
            if response.status_code == 401:
                if await self.refresh_access_token():
                    return await self.create_lead(name, contact_id, application_type, school, student_class)
            
            print(f"Failed to create lead: {response.status_code} - {response.text}")
            return None
    
    async def _get_or_create_tag(self, tag_name: str) -> Optional[int]:
        """
        Получение или создание тега в AMO CRM
        Возвращает ID тега или None при ошибке
        
        В AMO API v4 теги добавляются по имени напрямую в _embedded.tags
        """
        url = f"{self.base_url}/api/v4/leads/tags"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Получаем список тегов
                response = await client.get(url, headers=self._get_headers())
                
                if response.status_code == 200:
                    data = response.json()
                    if "_embedded" in data and "tags" in data["_embedded"]:
                        tags_list = data["_embedded"]["tags"]
                        if isinstance(tags_list, list):
                            for tag in tags_list:
                                if tag.get("name") == tag_name:
                                    return tag.get("id")
                
                # Тег не найден, создаём новый
                create_url = f"{self.base_url}/api/v4/leads/tags"
                payload = [{"name": tag_name}]
                
                create_response = await client.post(
                    create_url,
                    headers=self._get_headers(),
                    json=payload
                )
                
                if create_response.status_code in [200, 201]:
                    create_data = create_response.json()
                    if "_embedded" in create_data and "tags" in create_data["_embedded"]:
                        tags_list = create_data["_embedded"]["tags"]
                        if isinstance(tags_list, list) and len(tags_list) > 0:
                            return tags_list[0].get("id")
                
            except (IndexError, KeyError, TypeError) as e:
                print(f"Error parsing tag response: {e}")
            except Exception as e:
                print(f"Error getting/creating tag: {e}")
            
            # Если не удалось получить ID, вернём None
            # В AMO можно добавлять теги по имени, они создадутся автоматически
            return None
    
    async def add_note_to_lead(self, lead_id: int, text: str) -> bool:
        """Добавление примечания к сделке"""
        url = f"{self.base_url}/api/v4/leads/{lead_id}/notes"
        
        payload = [{
            "note_type": "common",
            "params": {"text": text}
        }]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload
            )
            
            return response.status_code == 200


async def send_students_to_amo(student_ids: List[str] = None) -> Dict[str, Any]:
    """
    Отправка заявок учеников в AMO CRM
    
    Args:
        student_ids: Список ID студентов для отправки. 
                    Если None - отправляются все неотправленные.
    
    Returns:
        Словарь с результатами: успешные, неудачные, ошибки
    """
    amo_service = AMOCRMService()
    students_collection = await get_students_collection()
    
    # Формируем запрос
    query = {"sent_to_amo": False}
    if student_ids:
        query["_id"] = {"$in": [ObjectId(sid) for sid in student_ids]}
    
    students = await students_collection.find(query).to_list(length=100)
    
    results = {
        "success": [],
        "failed": [],
        "total": len(students)
    }
    
    for student in students:
        try:
            # Создаем контакт
            contact_id = await amo_service.create_contact(
                fio=student.get("fio", ""),
                phone=student.get("phone", "")
            )
            
            if not contact_id:
                results["failed"].append({
                    "id": str(student["_id"]),
                    "fio": student.get("fio", ""),
                    "error": "Failed to create contact"
                })
                continue
            
            # Создаем сделку
            lead_id = await amo_service.create_lead(
                name=student.get("fio", ""),
                contact_id=contact_id,
                application_type=student.get("application_type", ""),
                school=student.get("school", ""),
                student_class=student.get("class", "")
            )
            
            if not lead_id:
                results["failed"].append({
                    "id": str(student["_id"]),
                    "fio": student.get("fio", ""),
                    "error": "Failed to create lead"
                })
                continue
            
            # Добавляем примечание с информацией
            app_type = student.get("application_type", "")
            note_text = f"""Тип заявки: {app_type if app_type else "-"}
Школа: {student.get("school", "-")}
Класс: {student.get("class", "-")}
Телефон: {student.get("phone", "-")}
Дата заявки: {student.get("created_at", "-")}"""
            
            await amo_service.add_note_to_lead(lead_id, note_text)
            
            # Обновляем статус в БД
            await students_collection.update_one(
                {"_id": student["_id"]},
                {
                    "$set": {
                        "sent_to_amo": True,
                        "amo_contact_id": str(contact_id),
                        "amo_lead_id": str(lead_id)
                    }
                }
            )
            
            results["success"].append({
                "id": str(student["_id"]),
                "fio": student.get("fio", ""),
                "amo_contact_id": contact_id,
                "amo_lead_id": lead_id
            })
            
        except Exception as e:
            print(f"Error sending student {student['_id']} to AMO: {e}")
            results["failed"].append({
                "id": str(student["_id"]),
                "fio": student.get("fio", ""),
                "error": str(e)
            })
    
    return results

