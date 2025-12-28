import httpx
import asyncio
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
        student_class: str = "",
        parent_contact_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Создание сделки (лида) в AMO CRM
        Возвращает ID созданной сделки или None при ошибке
        
        Args:
            name: Имя для сделки (не используется, формируется автоматически)
            contact_id: ID контакта ученика
            application_type: Тип заявки
            school: Школа
            student_class: Класс
            parent_contact_id: ID контакта родителя (опционально)
        """
        from datetime import datetime
        
        url = f"{self.base_url}/api/v4/leads"
        
        # Формируем название заявки: тип + дата
        today = datetime.now().strftime("%d.%m.%Y")
        lead_name = f"Заявка {application_type} {today}" if application_type else f"Заявка {today}"
        
        # Формируем список контактов
        contacts = [{"id": contact_id}]
        if parent_contact_id:
            contacts.append({"id": parent_contact_id})
        
        lead_data = {
            "name": lead_name,
            "_embedded": {
                "contacts": contacts
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
                    return await self.create_lead(name, contact_id, application_type, school, student_class, parent_contact_id)
            
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
    
    async def update_lead_pipeline(self, lead_id: int, pipeline_id: int, status_id: Optional[int] = None) -> bool:
        """
        Перенос сделки в нужную воронку
        
        Args:
            lead_id: ID сделки
            pipeline_id: ID воронки
            status_id: ID статуса в воронке (опционально, если не указан - первый статус)
        
        Returns:
            True если успешно, False при ошибке
        """
        url = f"{self.base_url}/api/v4/leads"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Если status_id не указан, получаем первый статус из воронки
            if status_id is None:
                # Получаем информацию о воронке
                pipelines_url = f"{self.base_url}/api/v4/leads/pipelines/{pipeline_id}"
                pipelines_response = await client.get(
                    pipelines_url,
                    headers=self._get_headers()
                )
                if pipelines_response.status_code == 200:
                    pipeline_data = pipelines_response.json()
                    if "_embedded" in pipeline_data and "statuses" in pipeline_data["_embedded"]:
                        statuses = pipeline_data["_embedded"]["statuses"]
                        if statuses and len(statuses) > 0:
                            status_id = statuses[0].get("id")
            
            if status_id is None:
                print(f"Warning: Could not determine status_id for pipeline {pipeline_id}")
                return False
            
            payload = [{
                "id": lead_id,
                "pipeline_id": pipeline_id,
                "status_id": status_id
            }]
            response = await client.patch(
                url,
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code == 200:
                return True
            
            if response.status_code == 401:
                if await self.refresh_access_token():
                    return await self.update_lead_pipeline(lead_id, pipeline_id, status_id)
            
            print(f"Failed to update lead pipeline: {response.status_code} - {response.text}")
            return False
    
    async def get_lead_contacts(self, lead_id: int) -> List[int]:
        """
        Получение списка ID контактов сделки
        
        Returns:
            Список ID контактов или пустой список при ошибке
        """
        url = f"{self.base_url}/api/v4/leads/{lead_id}?with=contacts"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    contact_ids = []
                    
                    # Проверяем _embedded.contacts
                    if "_embedded" in data and "contacts" in data["_embedded"]:
                        contacts = data["_embedded"]["contacts"]
                        for contact in contacts:
                            contact_id = contact.get("id")
                            if contact_id:
                                contact_ids.append(contact_id)
                    
                    # Если контактов нет в _embedded, пробуем через links
                    if not contact_ids:
                        links_url = f"{self.base_url}/api/v4/leads/{lead_id}/links"
                        links_response = await client.get(
                            links_url,
                            headers=self._get_headers()
                        )
                        if links_response.status_code == 200:
                            links_data = links_response.json()
                            if "_embedded" in links_data and "links" in links_data["_embedded"]:
                                links = links_data["_embedded"]["links"]
                                for link in links:
                                    if link.get("to_entity_type") == "contacts":
                                        contact_id = link.get("to_entity_id")
                                        if contact_id:
                                            contact_ids.append(contact_id)
                    
                    return contact_ids
                
                if response.status_code == 401:
                    if await self.refresh_access_token():
                        return await self.get_lead_contacts(lead_id)
                
                return []
            except Exception as e:
                print(f"Exception getting lead contacts {lead_id}: {e}")
                return []
    
    async def add_contact_to_lead(self, lead_id: int, contact_id: int) -> bool:
        """
        Добавление контакта к сделке через POST /api/v4/leads/{leadId}/link
        
        Returns:
            True если успешно, False при ошибке
        """
        # Сначала проверяем, не добавлен ли контакт уже
        lead_info_url = f"{self.base_url}/api/v4/leads/{lead_id}?with=contacts"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Получаем текущие контакты
            lead_response = await client.get(lead_info_url, headers=self._get_headers())
            
            existing_contact_ids = []
            if lead_response.status_code == 200:
                lead_data = lead_response.json()
                # Проверяем как в корне, так и в _embedded
                if "contacts" in lead_data and isinstance(lead_data["contacts"], list):
                    existing_contact_ids = [c.get("id") for c in lead_data["contacts"] if c.get("id")]
                elif "_embedded" in lead_data and "contacts" in lead_data["_embedded"]:
                    existing_contact_ids = [c.get("id") for c in lead_data["_embedded"]["contacts"] if c.get("id")]
            
            # Если контакт уже есть, возвращаем True
            if contact_id in existing_contact_ids:
                return True
            
            # Используем правильный endpoint: POST /api/v4/leads/{leadId}/link
            link_url = f"{self.base_url}/api/v4/leads/{lead_id}/link"
            link_payload = [{
                "to_entity_id": contact_id,
                "to_entity_type": "contacts"
            }]
            
            response = await client.post(
                link_url,
                headers=self._get_headers(),
                json=link_payload
            )
            
            if response.status_code in [200, 201]:
                # Небольшая задержка для обновления данных в AMO
                import asyncio
                await asyncio.sleep(2)  # Увеличиваем задержку для надежности
                
                # МНОЖЕСТВЕННАЯ ПРОВЕРКА: проверяем несколько раз с задержками
                max_attempts = 3
                for attempt in range(max_attempts):
                    verify_response = await client.get(lead_info_url, headers=self._get_headers())
                    if verify_response.status_code == 200:
                        verify_data = verify_response.json()
                        verify_contact_ids = []
                        if "contacts" in verify_data and isinstance(verify_data["contacts"], list):
                            verify_contact_ids = [c.get("id") for c in verify_data["contacts"] if c.get("id")]
                        elif "_embedded" in verify_data and "contacts" in verify_data["_embedded"]:
                            verify_contact_ids = [c.get("id") for c in verify_data["_embedded"]["contacts"] if c.get("id")]
                        
                        if contact_id in verify_contact_ids:
                            print(f"✅ Contact {contact_id} successfully added to lead {lead_id} (attempt {attempt + 1})")
                            return True
                    
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(1)  # Ждем перед следующей попыткой
                
                # Если после всех попыток контакт не найден, пробуем альтернативный способ проверки
                # Получаем сделку через /api/v4/leads с фильтром
                alternative_url = f"{self.base_url}/api/v4/leads/{lead_id}?with=contacts"
                alternative_response = await client.get(alternative_url, headers=self._get_headers())
                if alternative_response.status_code == 200:
                    alt_data = alternative_response.json()
                    alt_contact_ids = []
                    if "contacts" in alt_data and isinstance(alt_data["contacts"], list):
                        alt_contact_ids = [c.get("id") for c in alt_data["contacts"] if c.get("id")]
                    elif "_embedded" in alt_data and "contacts" in alt_data["_embedded"]:
                        alt_contact_ids = [c.get("id") for c in alt_data["_embedded"]["contacts"] if c.get("id")]
                    
                    if contact_id in alt_contact_ids:
                        print(f"✅ Contact {contact_id} found via alternative check")
                        return True
                
                print(f"❌ Warning: Contact {contact_id} was not found in lead {lead_id} after {max_attempts} attempts")
                print(f"   Response status: {response.status_code}")
                print(f"   Response body: {response.text[:200] if response.text else 'empty'}")
                return False
            
            if response.status_code == 401:
                if await self.refresh_access_token():
                    return await self.add_contact_to_lead(lead_id, contact_id)
            
            print(f"Failed to add contact to lead: {response.status_code} - {response.text}")
            return False
            
            if response.status_code == 401:
                if await self.refresh_access_token():
                    return await self.add_contact_to_lead(lead_id, contact_id)
            
            print(f"Failed to add contact to lead: {response.status_code} - {response.text}")
            return False
    
    async def get_lead_notes(self, lead_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка заметок сделки
        
        Returns:
            Список заметок или пустой список при ошибке
        """
        url = f"{self.base_url}/api/v4/leads/{lead_id}/notes"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "_embedded" in data and "notes" in data["_embedded"]:
                        return data["_embedded"]["notes"]
                
                if response.status_code == 401:
                    if await self.refresh_access_token():
                        return await self.get_lead_notes(lead_id)
                
                return []
            except Exception as e:
                print(f"Exception getting lead notes {lead_id}: {e}")
                return []
    
    async def check_lead_exists(self, lead_id: int) -> bool:
        """
        Проверка существования сделки в AMO CRM по ID
        Возвращает True если сделка существует, False если нет
        """
        url = f"{self.base_url}/api/v4/leads/{lead_id}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    return True
                elif response.status_code == 404:
                    return False
                elif response.status_code == 401:
                    # Попробуем обновить токен и повторить
                    if await self.refresh_access_token():
                        response = await client.get(
                            url,
                            headers=self._get_headers()
                        )
                        return response.status_code == 200
                    return False
                else:
                    print(f"Error checking lead {lead_id}: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"Exception checking lead {lead_id}: {e}")
                return False
    
    async def search_contacts_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """
        Поиск контактов по телефону в AMO CRM
        Возвращает список контактов с указанным телефоном
        """
        url = f"{self.base_url}/api/v4/contacts"
        
        # Нормализуем телефон (убираем все кроме цифр)
        phone_normalized = ''.join(filter(str.isdigit, phone))
        
        if not phone_normalized or len(phone_normalized) < 10:
            return []
        
        # Используем последние 10 цифр для поиска (российские номера)
        phone_search = phone_normalized[-10:] if len(phone_normalized) > 10 else phone_normalized
        
        # Поиск контактов по телефону через query параметр (AMO API ищет по всем полям)
        params = {
            "query": phone_search,
            "limit": 250
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    contacts = []
                    
                    if "_embedded" in data and "contacts" in data["_embedded"]:
                        all_contacts = data["_embedded"]["contacts"]
                        
                        for contact in all_contacts:
                            # Проверяем, что телефон действительно совпадает
                            phone_matches = False
                            if "custom_fields_values" in contact:
                                for field in contact["custom_fields_values"]:
                                    if field.get("field_code") == "PHONE":
                                        for value in field.get("values", []):
                                            contact_phone = ''.join(filter(str.isdigit, str(value.get("value", ""))))
                                            # Сравниваем последние 10 цифр
                                            contact_phone_search = contact_phone[-10:] if len(contact_phone) > 10 else contact_phone
                                            if contact_phone_search == phone_search:
                                                phone_matches = True
                                                break
                                    if phone_matches:
                                        break
                            
                            if phone_matches:
                                contacts.append(contact)
                    
                    return contacts
                
                if response.status_code == 401:
                    if await self.refresh_access_token():
                        return await self.search_contacts_by_phone(phone)
                
                return []
            except Exception as e:
                print(f"Error searching contacts by phone: {e}")
                return []
    
    async def get_contact_leads(self, contact_id: int, pipeline_id: int = None, tag_id: int = None) -> List[Dict[str, Any]]:
        """
        Получение сделок контакта с полной информацией (включая теги)
        Использует фильтры для сужения выборки
        
        Args:
            contact_id: ID контакта
            pipeline_id: ID воронки для фильтрации (опционально)
            tag_id: ID тега для фильтрации (опционально)
        """
        url = f"{self.base_url}/api/v4/leads"
        # Используем фильтр по контакту и параметр with для получения связанных данных (тегов)
        params = {
            "filter[contacts]": contact_id,
            "with": "tags"
        }
        
        # Добавляем фильтр по воронке, если указан
        if pipeline_id:
            params["filter[pipeline_id]"] = pipeline_id
        
        # Добавляем фильтр по тегу, если указан
        if tag_id:
            params["filter[tags]"] = tag_id
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "_embedded" in data and "leads" in data["_embedded"]:
                        leads = data["_embedded"]["leads"]
                        return leads
                    return []
                
                if response.status_code == 401:
                    if await self.refresh_access_token():
                        return await self.get_contact_leads(contact_id, pipeline_id, tag_id)
                
                return []
            except Exception as e:
                print(f"Error getting contact leads: {e}")
                return []
    
    async def find_lead_by_phone(self, phone: str, required_tag: str = None, application_type: str = None) -> Optional[Dict[str, Any]]:
        """
        Поиск сделки по телефону в правильной воронке с нужным тегом
        
        Args:
            phone: Номер телефона для поиска
            required_tag: Обязательный тег для сделки (по умолчанию "МК кибербез")
        
        Returns:
            Словарь с информацией о найденной сделке или None
            {
                "lead_id": int,
                "pipeline_id": int,
                "has_tag": bool,
                "tags": list
            }
        """
        correct_pipeline_id = settings.amo_correct_pipeline_id
        
        # Ищем контакты по телефону
        contacts = await self.search_contacts_by_phone(phone)
        
        if not contacts:
            return None
        
        # Получаем ID тега заранее, если требуется
        required_tag_id = None
        if required_tag:
            required_tag_id = await self._get_or_create_tag(required_tag)
        
        # Для каждого контакта проверяем его сделки
        for contact in contacts:
            contact_id = contact.get("id")
            if not contact_id:
                continue
            
            # Получаем сделки с фильтрами: только в правильной воронке и с нужным тегом (если указан)
            # Это значительно сужает выборку и ускоряет поиск
            leads = await self.get_contact_leads(contact_id, pipeline_id=correct_pipeline_id, tag_id=required_tag_id)
            
            # Если сделки найдены с фильтрами, они уже в правильной воронке
            # Проверяем только наличие тега (если требуется)
            for lead in leads:
                lead_id = lead.get("id")
                pipeline_id = lead.get("pipeline_id")
                
                # Дополнительная проверка воронки (на случай если фильтр не сработал)
                if pipeline_id != correct_pipeline_id:
                    continue
                
                # Проверяем наличие тега
                # Теги могут быть в _embedded.tags или в поле tags
                tags = []
                if "_embedded" in lead and "tags" in lead["_embedded"]:
                    tags = lead["_embedded"]["tags"]
                elif "tags" in lead:
                    tags = lead["tags"] if isinstance(lead["tags"], list) else []
                
                tag_names = []
                tag_ids = []
                for tag in tags:
                    if isinstance(tag, dict):
                        tag_name = tag.get("name", "")
                        tag_id = tag.get("id")
                        tag_names.append(tag_name)
                        if tag_id:
                            tag_ids.append(tag_id)
                    elif isinstance(tag, str):
                        tag_names.append(tag)
                
                # Проверяем наличие тега по названию или по ID
                # Если использовали фильтр по тегу, сделка уже имеет нужный тег
                has_tag = False
                if required_tag:
                    # Если использовали фильтр по тегу, сделка уже имеет нужный тег
                    if required_tag_id and required_tag_id in tag_ids:
                        has_tag = True
                    else:
                        # Проверяем по названию (на случай если фильтр не сработал)
                        has_tag = required_tag in tag_names
                else:
                    # Если тег не требуется, считаем что тег есть (проверяем только воронку)
                    has_tag = True
                
                # Если сделка в правильной воронке, возвращаем её, даже если тег отсутствует
                # (тег мог быть не установлен при создании или удален позже)
                # Это позволяет находить сделки даже после дедупликации или если тег был удален
                return {
                    "lead_id": lead_id,
                    "pipeline_id": pipeline_id,
                    "has_tag": has_tag,
                    "tags": tag_names,
                    "contact_id": contact_id
                }
        
        return None
    
    async def get_lead_info(self, lead_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение информации о сделке в AMO CRM по ID
        Возвращает словарь с информацией о сделке или None при ошибке
        
        Возвращает:
        {
            "exists": True/False,
            "pipeline_id": int или None,
            "is_correct_pipeline": True/False,
            "is_hidden": True/False (если сделка в скрытой воронке)
        }
        """
        url = f"{self.base_url}/api/v4/leads/{lead_id}"
        correct_pipeline_id = settings.amo_correct_pipeline_id
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # AMO API v4 может возвращать сделки в _embedded.leads (при запросе списка)
                    # или в корне ответа (при запросе одной сделки GET /api/v4/leads/{id})
                    lead = None
                    if "_embedded" in data and "leads" in data["_embedded"]:
                        leads = data["_embedded"]["leads"]
                        if leads and len(leads) > 0:
                            lead = leads[0]
                    elif "pipeline_id" in data or "id" in data:
                        # Сделка в корне ответа (GET /api/v4/leads/{id})
                        lead = data
                    
                    if lead:
                        pipeline_id = lead.get("pipeline_id")
                        
                        # Проверяем, правильная ли воронка
                        if pipeline_id is not None:
                            is_correct_pipeline = pipeline_id == correct_pipeline_id
                        else:
                            # pipeline_id = None, не можем определить
                            is_correct_pipeline = None
                        
                        return {
                            "exists": True,
                            "pipeline_id": pipeline_id,
                            "is_correct_pipeline": is_correct_pipeline,
                            "is_hidden": False  # Если сделка найдена, она не скрыта
                        }
                    
                    # Если структура ответа неожиданная, но статус 200
                    # Не можем определить воронку, но сделка существует
                    return {
                        "exists": True,
                        "pipeline_id": None,
                        "is_correct_pipeline": None,  # Неизвестно, не обновляем статус
                        "is_hidden": False
                    }
                    
                elif response.status_code == 404:
                    return {
                        "exists": False,
                        "pipeline_id": None,
                        "is_correct_pipeline": False,
                        "is_hidden": False
                    }
                elif response.status_code == 204:
                    # 204 No Content - сделка существует, но API не возвращает тело ответа
                    # Попробуем получить информацию через список сделок с фильтром по ID
                    # Используем параметр with для получения дополнительных полей
                    list_url = f"{self.base_url}/api/v4/leads?filter[id]={lead_id}&with=pipelines"
                    list_response = await client.get(
                        list_url,
                        headers=self._get_headers()
                    )
                    
                    if list_response.status_code == 200:
                        list_data = list_response.json()
                        if "_embedded" in list_data and "leads" in list_data["_embedded"]:
                            leads = list_data["_embedded"]["leads"]
                            if leads and len(leads) > 0:
                                lead = leads[0]
                                pipeline_id = lead.get("pipeline_id")
                                is_correct_pipeline = pipeline_id == correct_pipeline_id
                                
                                return {
                                    "exists": True,
                                    "pipeline_id": pipeline_id,
                                    "is_correct_pipeline": is_correct_pipeline,
                                    "is_hidden": False
                                }
                    
                    # Если через список тоже не получилось, попробуем без фильтра, но с лимитом 1
                    # и проверим, есть ли наша сделка в результатах
                    simple_list_url = f"{self.base_url}/api/v4/leads?limit=250"
                    simple_list_response = await client.get(
                        simple_list_url,
                        headers=self._get_headers()
                    )
                    
                    if simple_list_response.status_code == 200:
                        simple_list_data = simple_list_response.json()
                        if "_embedded" in simple_list_data and "leads" in simple_list_data["_embedded"]:
                            leads = simple_list_data["_embedded"]["leads"]
                            # Ищем нашу сделку по ID
                            for lead in leads:
                                if lead.get("id") == lead_id:
                                    pipeline_id = lead.get("pipeline_id")
                                    is_correct_pipeline = pipeline_id == correct_pipeline_id
                                    
                                    return {
                                        "exists": True,
                                        "pipeline_id": pipeline_id,
                                        "is_correct_pipeline": is_correct_pipeline,
                                        "is_hidden": False
                                    }
                    
                    # Если через список тоже не получилось, считаем что сделка скрыта
                    # Но НЕ обновляем статус на неотправленную, так как сделка существует
                    return {
                        "exists": True,  # Сделка существует, но недоступна для проверки воронки
                        "pipeline_id": None,
                        "is_correct_pipeline": None,  # Неизвестно, не обновляем статус
                        "is_hidden": True
                    }
                elif response.status_code == 403:
                    # 403 может означать, что сделка в скрытой воронке
                    return {
                        "exists": True,  # Сделка существует, но недоступна
                        "pipeline_id": None,
                        "is_correct_pipeline": False,
                        "is_hidden": True
                    }
                elif response.status_code == 401:
                    # Попробуем обновить токен и повторить
                    if await self.refresh_access_token():
                        response = await client.get(
                            url,
                            headers=self._get_headers()
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if "_embedded" in data and "leads" in data["_embedded"]:
                                leads = data["_embedded"]["leads"]
                                if leads and len(leads) > 0:
                                    lead = leads[0]
                                    pipeline_id = lead.get("pipeline_id")
                                    is_correct_pipeline = pipeline_id == correct_pipeline_id
                                    return {
                                        "exists": True,
                                        "pipeline_id": pipeline_id,
                                        "is_correct_pipeline": is_correct_pipeline,
                                        "is_hidden": False
                                    }
                    return None
                else:
                    print(f"Error getting lead info {lead_id}: {response.status_code} - {response.text}")
                    return None
            except Exception as e:
                print(f"Exception getting lead info {lead_id}: {e}")
                return None


async def _send_single_student_to_amo(
    amo_service: AMOCRMService,
    students_collection,
    student: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Отправка одной заявки в AMO CRM
    Возвращает результат: {"success": True/False, "data": {...}, "error": "..."}
    """
    try:
        # Создаем контакт ученика
        contact_id = await amo_service.create_contact(
            fio=student.get("fio", ""),
            phone=student.get("phone", "")
        )
        
        if not contact_id:
            return {
                "success": False,
                "id": str(student["_id"]),
                "fio": student.get("fio", ""),
                "error": "Failed to create contact"
            }
        
        # Создаем контакт родителя, если есть данные
        parent_contact_id = None
        parent_name = student.get("parent_name") or ""
        parent_name = parent_name.strip() if isinstance(parent_name, str) else ""
        parent_phone = student.get("parent_phone") or ""
        parent_phone = parent_phone.strip() if isinstance(parent_phone, str) else ""
        
        if parent_name and parent_phone:
            parent_contact_id = await amo_service.create_contact(
                fio=parent_name,
                phone=parent_phone
            )
            # Если не удалось создать контакт родителя, продолжаем без него
            if not parent_contact_id:
                print(f"Warning: Failed to create parent contact for student {student.get('_id')}")
        
        # Создаем сделку
        lead_id = await amo_service.create_lead(
            name=student.get("fio", ""),
            contact_id=contact_id,
            application_type=student.get("application_type", ""),
            school=student.get("school", ""),
            student_class=student.get("class", ""),
            parent_contact_id=parent_contact_id
        )
        
        if not lead_id:
            return {
                "success": False,
                "id": str(student["_id"]),
                "fio": student.get("fio", ""),
                "error": "Failed to create lead"
            }
        
        # Добавляем примечание с информацией
        app_type = student.get("application_type", "")
        note_text = f"""Тип заявки: {app_type if app_type else "-"}
Школа: {student.get("school", "-")}
Класс: {student.get("class", "-")}
Телефон: {student.get("phone", "-")}"""
        
        # Добавляем информацию о родителе, если есть
        if parent_name and parent_phone:
            note_text += f"""
Родитель: {parent_name}
Телефон родителя: {parent_phone}"""
        
        note_text += f"""
Дата заявки: {student.get("created_at", "-")}"""
        
        await amo_service.add_note_to_lead(lead_id, note_text)
        
        # Обновляем статус в БД
        update_data = {
            "sent_to_amo": True,
            "amo_contact_id": str(contact_id),
            "amo_lead_id": str(lead_id)
        }
        
        # Сохраняем ID контакта родителя, если он был создан
        if parent_contact_id:
            update_data["amo_parent_contact_id"] = str(parent_contact_id)
        
        await students_collection.update_one(
            {"_id": student["_id"]},
            {"$set": update_data}
        )
        
        return {
            "success": True,
            "id": str(student["_id"]),
            "fio": student.get("fio", ""),
            "amo_contact_id": contact_id,
            "amo_lead_id": lead_id,
            "amo_parent_contact_id": parent_contact_id
        }
        
    except Exception as e:
        print(f"Error sending student {student['_id']} to AMO: {e}")
        return {
            "success": False,
            "id": str(student["_id"]),
            "fio": student.get("fio", ""),
            "error": str(e)
        }


async def send_students_to_amo(student_ids: List[str] = None) -> Dict[str, Any]:
    """
    Отправка заявок учеников в AMO CRM с параллельной обработкой
    
    Args:
        student_ids: Список ID студентов для отправки. 
                    Если None - отправляются все неотправленные.
    
    Returns:
        Словарь с результатами: успешные, неудачные, ошибки
    """
    amo_service = AMOCRMService()
    students_collection = await get_students_collection()
    
    # Формируем запрос
    # Если указаны конкретные ID - отправляем их независимо от статуса (для повторной отправки)
    # Если ID не указаны - отправляем только неотправленные
    if student_ids:
        query = {"_id": {"$in": [ObjectId(sid) for sid in student_ids]}}
    else:
        query = {"sent_to_amo": False}
    
    students = await students_collection.find(query).to_list(length=100)
    
    results = {
        "success": [],
        "failed": [],
        "total": len(students)
    }
    
    if not students:
        return results
    
    # Обрабатываем заявки батчами для соблюдения лимитов AMO API
    # AMO обычно позволяет ~7-10 запросов в секунду, используем батчи по 5
    BATCH_SIZE = 5
    
    # Создаем задачи для всех студентов
    tasks = [
        _send_single_student_to_amo(amo_service, students_collection, student)
        for student in students
    ]
    
    # Обрабатываем батчами
    for i in range(0, len(tasks), BATCH_SIZE):
        batch = tasks[i:i + BATCH_SIZE]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        
        for result in batch_results:
            if isinstance(result, Exception):
                results["failed"].append({
                    "id": "unknown",
                    "fio": "unknown",
                    "error": str(result)
                })
            elif result.get("success"):
                results["success"].append({
                    "id": result["id"],
                    "fio": result["fio"],
                    "amo_contact_id": result.get("amo_contact_id"),
                    "amo_lead_id": result.get("amo_lead_id")
                })
            else:
                results["failed"].append({
                    "id": result.get("id", "unknown"),
                    "fio": result.get("fio", "unknown"),
                    "error": result.get("error", "Unknown error")
                })
        
        # Небольшая задержка между батчами для соблюдения rate limit
        if i + BATCH_SIZE < len(tasks):
            await asyncio.sleep(0.5)
    
    return results


async def verify_sent_to_amo(check_all: bool = False) -> Dict[str, Any]:
    """
    Проверка всех заявок, помеченных как отправленные в AMO CRM.
    Проверяет:
    1. Существует ли сделка в AMO
    2. Находится ли сделка в правильной воронке (pipeline_id = 7797890)
    3. Не находится ли сделка в скрытой воронке
    
    Если сделка не найдена, в неправильной воронке или скрыта - обновляет статус на неотправленную.
    
    Args:
        check_all: Если True, проверяет все заявки с amo_lead_id (включая помеченные как неотправленные)
    
    Returns:
        Словарь с результатами: проверено, не найдено, неправильная воронка, скрыта, обновлено
    """
    amo_service = AMOCRMService()
    students_collection = await get_students_collection()
    
    # Получаем все заявки с amo_lead_id
    if check_all:
        query = {"amo_lead_id": {"$exists": True, "$ne": None}}
    else:
        query = {"sent_to_amo": True, "amo_lead_id": {"$exists": True, "$ne": None}}
    students = await students_collection.find(query).to_list(length=None)
    
    results = {
        "checked": 0,
        "not_found": [],
        "wrong_pipeline": [],
        "hidden": [],
        "updated": 0,
        "errors": []
    }
    
    if not students:
        return results
    
    # Обрабатываем батчами для соблюдения rate limit
    BATCH_SIZE = 5
    
    for i in range(0, len(students), BATCH_SIZE):
        batch = students[i:i + BATCH_SIZE]
        
        # Проверяем каждую заявку в батче
        for student in batch:
            try:
                results["checked"] += 1
                lead_id_str = student.get("amo_lead_id")
                
                if not lead_id_str:
                    continue
                
                # Преобразуем ID в int
                try:
                    lead_id = int(lead_id_str)
                except (ValueError, TypeError):
                    results["errors"].append({
                        "id": str(student["_id"]),
                        "fio": student.get("fio", ""),
                        "error": f"Invalid lead_id: {lead_id_str}"
                    })
                    continue
                
                # Получаем информацию о сделке (включая воронку)
                lead_info = await amo_service.get_lead_info(lead_id)
                
                if lead_info is None:
                    # Ошибка при получении информации
                    results["errors"].append({
                        "id": str(student["_id"]),
                        "fio": student.get("fio", ""),
                        "error": "Failed to get lead info"
                    })
                    continue
                
                # Проверяем различные случаи
                should_update_to_false = False
                should_update_to_true = False
                reason = ""
                current_sent_status = student.get("sent_to_amo", False)
                
                if not lead_info.get("exists", False):
                    # Сделка не найдена
                    results["not_found"].append({
                        "id": str(student["_id"]),
                        "fio": student.get("fio", ""),
                        "amo_lead_id": lead_id_str
                    })
                    should_update_to_false = True
                    reason = "not_found"
                elif lead_info.get("is_hidden", False):
                    # Сделка в скрытой воронке
                    results["hidden"].append({
                        "id": str(student["_id"]),
                        "fio": student.get("fio", ""),
                        "amo_lead_id": lead_id_str,
                        "pipeline_id": lead_info.get("pipeline_id")
                    })
                    should_update_to_false = True
                    reason = "hidden"
                elif lead_info.get("is_correct_pipeline") is False:
                    # Сделка в неправильной воронке (явно False, не None)
                    results["wrong_pipeline"].append({
                        "id": str(student["_id"]),
                        "fio": student.get("fio", ""),
                        "amo_lead_id": lead_id_str,
                        "current_pipeline_id": lead_info.get("pipeline_id"),
                        "correct_pipeline_id": settings.amo_correct_pipeline_id
                    })
                    should_update_to_false = True
                    reason = "wrong_pipeline"
                elif lead_info.get("is_correct_pipeline") is None:
                    # Не удалось определить воронку (pipeline_id = None, но сделка существует)
                    # Не обновляем статус, так как мы не знаем, правильная ли воронка
                    continue  # Пропускаем эту заявку, не обновляем статус
                elif lead_info.get("is_correct_pipeline") is True:
                    # Сделка найдена и в правильной воронке - восстанавливаем статус если нужно
                    if not current_sent_status:
                        should_update_to_true = True
                        reason = "restored"
                
                if should_update_to_false:
                    # Обновляем статус в БД на False
                    await students_collection.update_one(
                        {"_id": student["_id"]},
                        {
                            "$set": {
                                "sent_to_amo": False
                            }
                        }
                    )
                    results["updated"] += 1
                elif should_update_to_true:
                    # Обновляем статус в БД на True (восстанавливаем)
                    await students_collection.update_one(
                        {"_id": student["_id"]},
                        {
                            "$set": {
                                "sent_to_amo": True
                            }
                        }
                    )
                    results["updated"] += 1
                    
            except Exception as e:
                print(f"Error verifying student {student.get('_id')}: {e}")
                results["errors"].append({
                    "id": str(student.get("_id", "unknown")),
                    "fio": student.get("fio", ""),
                    "error": str(e)
                })
        
        # Небольшая задержка между батчами
        if i + BATCH_SIZE < len(students):
            await asyncio.sleep(0.5)
    
    return results
