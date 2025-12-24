from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, handler):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {"type": "string"}


class StudentBase(BaseModel):
    fio: str = Field(..., description="ФИО ученика")
    school: str = Field(..., description="Школа")
    student_class: str = Field(..., alias="class", description="Класс")
    phone: str = Field(..., description="Номер телефона")
    application_type: str = Field(..., description="Тип заявки")
    # Опциональные поля для мастер-класса по кибербезопасности
    parent_name: Optional[str] = Field(None, description="Имя родителя")
    parent_phone: Optional[str] = Field(None, description="Телефон родителя")
    # Поля обратной связи (вторая страница анкеты)
    masterclass_rating: Optional[int] = Field(None, description="Оценка мастер-класса (1-10)")
    speaker_rating: Optional[int] = Field(None, description="Оценка спикера (1-10)")
    feedback: Optional[str] = Field(None, description="Свободная форма обратной связи")


class StudentCreate(StudentBase):
    pass


class StudentInDB(StudentBase):
    id: str = Field(default=None, alias="_id")
    image_paths: Optional[list[str]] = Field(default=None, description="Пути к изображениям (может быть несколько)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_to_amo: bool = False
    amo_contact_id: Optional[str] = None
    amo_lead_id: Optional[str] = None
    ocr_raw: Optional[dict] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class StudentResponse(BaseModel):
    id: str
    fio: str
    school: str
    student_class: str = Field(..., alias="class")
    phone: str
    image_paths: Optional[list[str]] = None
    created_at: datetime
    sent_to_amo: bool
    amo_contact_id: Optional[str] = None
    amo_lead_id: Optional[str] = None
    application_type: str = ""
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    masterclass_rating: Optional[int] = None
    speaker_rating: Optional[int] = None
    feedback: Optional[str] = None

    class Config:
        populate_by_name = True


class OCRResult(BaseModel):
    fio: str = ""
    school: str = ""
    student_class: str = Field(default="", alias="class")
    phone: str = ""
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    raw_response: Optional[dict] = None

    class Config:
        populate_by_name = True


class FeedbackOCRResult(BaseModel):
    """Результат OCR для второй страницы (обратная связь)"""
    masterclass_rating: Optional[int] = None  # Оценка мастер-класса (1-10)
    speaker_rating: Optional[int] = None  # Оценка спикера (1-10)
    feedback: str = ""  # Свободная форма обратной связи
    raw_response: Optional[dict] = None

    class Config:
        populate_by_name = True

