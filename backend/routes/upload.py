import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from backend.services.ocr import process_image_ocr
from backend.database.mongodb import get_students_collection

router = APIRouter()

# Путь к директории загрузок
# На Render используем временную директорию, в production лучше использовать GridFS
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

# Создаем директорию для загрузок если не существует
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_photo(
    file: UploadFile = File(...),
    application_type: str = Form(...)
):
    """
    Загрузка фотографии с данными ученика и распознавание через OCR.
    
    - Принимает изображение (jpg, jpeg, png, webp)
    - Принимает тип заявки (application_type)
    - Обрабатывает через OCR (OpenRouter + Gemini)
    - Возвращает распознанные данные для редактирования (НЕ сохраняет в БД)
    
    Returns:
        Распознанные данные ученика (можно отредактировать перед сохранением)
    """
    # Проверяем тип файла
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый тип файла. Разрешены: {', '.join(allowed_types)}"
        )
    
    # Читаем содержимое файла
    contents = await file.read()
    
    # Проверяем размер (макс 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл слишком большой. Максимальный размер: 10MB"
        )
    
    # Генерируем уникальное имя файла
    file_extension = os.path.splitext(file.filename)[1] or ".jpg"
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Сохраняем файл временно (будет сохранён после редактирования)
    with open(file_path, "wb") as f:
        f.write(contents)
    
    try:
        # Обрабатываем через OCR
        ocr_result = await process_image_ocr(contents, file.filename)
        
        # Возвращаем данные для редактирования (НЕ сохраняем в БД)
        return {
            "success": True,
            "message": "Данные распознаны, проверьте и отредактируйте при необходимости",
            "image_path": file_path,  # Временный путь к файлу
            "data": {
                "fio": ocr_result.fio,
                "school": ocr_result.school,
                "class": ocr_result.student_class,
                "phone": ocr_result.phone
            },
            "ocr_raw": ocr_result.raw_response
        }
        
    except Exception as e:
        # Удаляем файл при ошибке
        if os.path.exists(file_path):
            os.remove(file_path)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка обработки изображения: {str(e)}"
        )


@router.post("/upload/save")
async def save_student_data(
    fio: str = Form(...),
    school: str = Form(...),
    student_class: str = Form(...),
    phone: str = Form(...),
    application_type: str = Form(...),
    image_path: str = Form(...),
    ocr_raw: Optional[str] = Form(None)
):
    """
    Сохранение данных ученика в БД после редактирования.
    
    Принимает отредактированные данные и сохраняет их в MongoDB.
    """
    import json
    
    # Парсим ocr_raw если передан
    ocr_raw_data = None
    if ocr_raw:
        try:
            ocr_raw_data = json.loads(ocr_raw)
        except:
            pass
    
    # Подготавливаем данные для сохранения
    student_data = {
        "fio": fio,
        "school": school,
        "class": student_class,
        "phone": phone,
        "application_type": application_type,
        "image_path": image_path,
        "created_at": datetime.utcnow(),
        "sent_to_amo": False,
        "amo_contact_id": None,
        "amo_lead_id": None,
        "ocr_raw": ocr_raw_data
    }
    
    # Сохраняем в MongoDB
    students_collection = await get_students_collection()
    result = await students_collection.insert_one(student_data)
    
    return {
        "success": True,
        "message": "Данные успешно сохранены",
        "student_id": str(result.inserted_id),
        "data": {
            "fio": fio,
            "school": school,
            "class": student_class,
            "phone": phone,
            "application_type": application_type
        }
    }


@router.post("/upload/manual")
async def upload_manual(
    fio: str,
    school: str,
    student_class: str,
    phone: str,
    application_type: str
):
    """
    Ручной ввод данных ученика (без OCR).
    Полезно для добавления данных вручную.
    """
    student_data = {
        "fio": fio,
        "school": school,
        "class": student_class,
        "phone": phone,
        "application_type": application_type,
        "image_path": None,
        "created_at": datetime.utcnow(),
        "sent_to_amo": False,
        "amo_contact_id": None,
        "amo_lead_id": None,
        "ocr_raw": None
    }
    
    students_collection = await get_students_collection()
    result = await students_collection.insert_one(student_data)
    
    return {
        "success": True,
        "message": "Данные успешно сохранены",
        "student_id": str(result.inserted_id),
        "data": {
            "fio": fio,
            "school": school,
            "class": student_class,
            "phone": phone
        }
    }

