from fastapi import APIRouter, HTTPException, status, Depends, Response, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional, List
from datetime import timedelta
from bson import ObjectId
import csv
import io
from backend.database.mongodb import get_students_collection
from backend.services.amo import send_students_to_amo, verify_sent_to_amo
from backend.utils.auth import authenticate_admin, get_current_admin, ACCESS_TOKEN_EXPIRE_MINUTES
from pydantic import BaseModel

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


class SendToAmoRequest(BaseModel):
    student_ids: Optional[List[str]] = None


@router.post("/login")
async def admin_login(request: LoginRequest, response: Response):
    """
    Авторизация администратора.
    Возвращает JWT токен при успешной авторизации.
    """
    token = authenticate_admin(request.password)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный пароль"
        )
    
    # Устанавливаем токен в cookie
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    
    return {
        "success": True,
        "token": token,
        "message": "Авторизация успешна"
    }


@router.post("/logout")
async def admin_logout(response: Response):
    """Выход из админ-панели"""
    response.delete_cookie("admin_token")
    return {"success": True, "message": "Выход выполнен"}


@router.get("/students")
async def get_students(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    sent_to_amo: Optional[bool] = None,
    search: Optional[str] = None,
    _: bool = Depends(get_current_admin)
):
    """
    Получение списка всех заявок учеников.
    
    Query params:
    - skip: Пропустить N записей (пагинация)
    - limit: Количество записей (макс 100)
    - sent_to_amo: Фильтр по статусу отправки в AMO
    - search: Поиск по ФИО
    """
    students_collection = await get_students_collection()
    
    # Формируем фильтр
    query = {}
    if sent_to_amo is not None:
        query["sent_to_amo"] = sent_to_amo
    if search:
        query["fio"] = {"$regex": search, "$options": "i"}
    
    # Ограничиваем limit
    limit = min(limit, 100)
    
    # Получаем общее количество
    total = await students_collection.count_documents(query)
    
    # Получаем записи
    cursor = students_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
    students = await cursor.to_list(length=limit)
    
    # Преобразуем ObjectId в строки
    result = []
    for student in students:
        student["id"] = str(student["_id"])
        student["_id"] = str(student["_id"])
        
        # Обратная совместимость: если есть image_path, но нет image_paths, создаём массив
        if "image_path" in student and "image_paths" not in student:
            student["image_paths"] = [student["image_path"]] if student.get("image_path") else []
        
        # Удаляем сырые данные OCR из ответа (они большие)
        student.pop("ocr_raw", None)
        result.append(student)
    
    return {
        "students": result,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/students/{student_id}")
async def get_student(
    student_id: str,
    _: bool = Depends(get_current_admin)
):
    """Получение данных конкретного ученика по ID"""
    students_collection = await get_students_collection()
    
    try:
        student = await students_collection.find_one({"_id": ObjectId(student_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат ID"
        )
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ученик не найден"
        )
    
    student["_id"] = str(student["_id"])
    return student


@router.delete("/students/{student_id}")
async def delete_student(
    student_id: str,
    _: bool = Depends(get_current_admin)
):
    """Удаление заявки ученика"""
    students_collection = await get_students_collection()
    
    try:
        result = await students_collection.delete_one({"_id": ObjectId(student_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат ID"
        )
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ученик не найден"
        )
    
    return {"success": True, "message": "Заявка удалена"}


@router.put("/students/{student_id}")
async def update_student(
    student_id: str,
    fio: Optional[str] = None,
    school: Optional[str] = None,
    student_class: Optional[str] = None,
    phone: Optional[str] = None,
    _: bool = Depends(get_current_admin)
):
    """Обновление данных ученика"""
    students_collection = await get_students_collection()
    
    update_data = {}
    if fio is not None:
        update_data["fio"] = fio
    if school is not None:
        update_data["school"] = school
    if student_class is not None:
        update_data["class"] = student_class
    if phone is not None:
        update_data["phone"] = phone
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет данных для обновления"
        )
    
    try:
        result = await students_collection.update_one(
            {"_id": ObjectId(student_id)},
            {"$set": update_data}
        )
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат ID"
        )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ученик не найден"
        )
    
    return {"success": True, "message": "Данные обновлены"}


@router.post("/send-to-amo")
async def send_to_amo(
    request: SendToAmoRequest,
    _: bool = Depends(get_current_admin)
):
    """
    Отправка заявок в AMO CRM.
    
    Body:
    - student_ids: Список ID учеников для отправки (опционально).
                   Если не указан - отправляются все неотправленные.
    """
    try:
        results = await send_students_to_amo(request.student_ids)
        
        return {
            "success": True,
            "message": f"Отправлено {len(results['success'])} из {results['total']} заявок",
            "results": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка отправки в AMO: {str(e)}"
        )


@router.get("/stats")
async def get_stats(_: bool = Depends(get_current_admin)):
    """Получение статистики по заявкам"""
    students_collection = await get_students_collection()
    
    total = await students_collection.count_documents({})
    sent = await students_collection.count_documents({"sent_to_amo": True})
    not_sent = await students_collection.count_documents({"sent_to_amo": False})
    
    return {
        "total": total,
        "sent_to_amo": sent,
        "not_sent": not_sent
    }


@router.post("/verify-amo")
async def verify_amo_status(_: bool = Depends(get_current_admin)):
    """
    Проверка всех заявок, помеченных как отправленные в AMO CRM.
    Если сделка не найдена в AMO, обновляет статус на неотправленную.
    """
    try:
        results = await verify_sent_to_amo()
        
        return {
            "success": True,
            "message": f"Проверено {results['checked']} заявок. Не найдено в AMO: {results['updated']}",
            "results": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка проверки AMO: {str(e)}"
        )


@router.get("/export-csv")
async def export_to_csv(
    sent_to_amo: Optional[bool] = None,
    search: Optional[str] = None,
    _: bool = Depends(get_current_admin)
):
    """
    Экспорт всех заявок в CSV файл.
    
    Query params:
    - sent_to_amo: Фильтр по статусу отправки в AMO
    - search: Поиск по ФИО
    """
    students_collection = await get_students_collection()
    
    # Формируем фильтр (аналогично get_students)
    query = {}
    if sent_to_amo is not None:
        query["sent_to_amo"] = sent_to_amo
    if search:
        query["fio"] = {"$regex": search, "$options": "i"}
    
    # Получаем все записи (без пагинации для экспорта)
    cursor = students_collection.find(query).sort("created_at", -1)
    students = await cursor.to_list(length=None)
    
    # Создаем CSV в памяти
    output = io.StringIO()
    
    # Заголовки CSV
    fieldnames = [
        "Тип заявки",
        "ФИО",
        "Школа",
        "Класс",
        "Телефон",
        "Имя родителя",
        "Телефон родителя",
        "Дата создания",
        "Отправлено в AMO",
        "ID контакта AMO",
        "ID сделки AMO",
        "Оценка мастер-класса",
        "Оценка спикера",
        "Отзыв"
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    
    # Записываем данные
    for student in students:
        # Форматируем дату
        created_at = student.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                date_str = created_at
            else:
                date_str = created_at.strftime("%d.%m.%Y %H:%M")
        else:
            date_str = ""
        
        # Форматируем статус отправки
        sent_status = "Да" if student.get("sent_to_amo", False) else "Нет"
        
        writer.writerow({
            "Тип заявки": student.get("application_type", ""),
            "ФИО": student.get("fio", ""),
            "Школа": student.get("school", ""),
            "Класс": student.get("class", ""),
            "Телефон": student.get("phone", ""),
            "Имя родителя": student.get("parent_name", "") or "",
            "Телефон родителя": student.get("parent_phone", "") or "",
            "Дата создания": date_str,
            "Отправлено в AMO": sent_status,
            "ID контакта AMO": student.get("amo_contact_id", "") or "",
            "ID сделки AMO": student.get("amo_lead_id", "") or "",
            "Оценка мастер-класса": student.get("masterclass_rating", "") or "",
            "Оценка спикера": student.get("speaker_rating", "") or "",
            "Отзыв": student.get("feedback", "") or ""
        })
    
    # Подготавливаем ответ с правильной кодировкой для Excel (UTF-8 с BOM)
    output.seek(0)
    csv_content = output.getvalue()
    
    # Добавляем BOM для корректного отображения в Excel
    csv_bytes = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')
    
    # Создаем поток для ответа
    csv_stream = io.BytesIO(csv_bytes)
    
    # Генерируем имя файла с датой
    from datetime import datetime
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([csv_stream.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

