import httpx
import base64
import json
from typing import Optional
from backend.config import get_settings
from backend.models.student import OCRResult

settings = get_settings()

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


async def process_image_ocr(image_data: bytes, filename: str) -> OCRResult:
    """
    Обрабатывает изображение через OpenRouter API с моделью Gemini 3 Pro
    и извлекает структурированные данные ученика.
    """
    # Конвертируем изображение в base64
    base64_image = base64.b64encode(image_data).decode("utf-8")
    
    # Определяем MIME тип
    mime_type = "image/jpeg"
    if filename.lower().endswith(".png"):
        mime_type = "image/png"
    elif filename.lower().endswith(".webp"):
        mime_type = "image/webp"
    elif filename.lower().endswith(".gif"):
        mime_type = "image/gif"
    
    # Формируем промпт для извлечения данных
    prompt = """Проанализируй изображение и извлеки данные ученика. 
На изображении должна быть информация о:
- ФИО (полное имя ученика)
- Школа (название школы)
- Класс (номер и буква класса, например "5А" или "11Б")
- Номер телефона

Верни данные ТОЛЬКО в формате JSON без дополнительного текста:
{
    "fio": "Фамилия Имя Отчество",
    "school": "Название школы",
    "class": "Класс",
    "phone": "Номер телефона"
}

Если какое-то поле не удалось распознать, оставь пустую строку.
Если это не изображение с данными ученика, верни пустые значения для всех полей."""

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ocr-crm.local",
        "X-Title": "OCR CRM"
    }
    
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            print(f"OpenRouter API error: {response.status_code} - {response.text}")
            return OCRResult(raw_response={"error": response.text})
        
        result = response.json()
        
        # Извлекаем текст ответа
        try:
            content = result["choices"][0]["message"]["content"]
            
            # Пытаемся распарсить JSON из ответа
            # Иногда модель может вернуть JSON обернутый в markdown блок
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            
            parsed_data = json.loads(json_str)
            
            return OCRResult(
                fio=parsed_data.get("fio", ""),
                school=parsed_data.get("school", ""),
                student_class=parsed_data.get("class", ""),
                phone=parsed_data.get("phone", ""),
                raw_response=result
            )
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error parsing OCR response: {e}")
            return OCRResult(raw_response=result)

