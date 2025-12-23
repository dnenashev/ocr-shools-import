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


class StudentCreate(StudentBase):
    pass


class StudentInDB(StudentBase):
    id: str = Field(default=None, alias="_id")
    image_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_to_amo: bool = False
    amo_contact_id: Optional[str] = None
    amo_lead_id: Optional[str] = None
    ocr_raw: Optional[dict] = None
    application_type: str = Field(default="", description="Тип заявки")

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
    image_path: Optional[str] = None
    created_at: datetime
    sent_to_amo: bool
    amo_contact_id: Optional[str] = None
    amo_lead_id: Optional[str] = None
    application_type: str = ""

    class Config:
        populate_by_name = True


class OCRResult(BaseModel):
    fio: str = ""
    school: str = ""
    student_class: str = Field(default="", alias="class")
    phone: str = ""
    raw_response: Optional[dict] = None

    class Config:
        populate_by_name = True

