from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .services.report_service import ReportService
from .services.template_compiler_service import TemplateCompilerService
from .services.text_template_service import TextTemplateService


def session(request: Request):
    with request.app.state.sessions() as db:
        yield db


def reports(db: Annotated[Session, Depends(session)]):
    return ReportService(db)


def templates(db: Annotated[Session, Depends(session)]):
    return TextTemplateService(db)


def compiler(db: Annotated[Session, Depends(session)]):
    return TemplateCompilerService(db)


ReportServiceDependency = Annotated[ReportService, Depends(reports)]
TextTemplateServiceDependency = Annotated[TextTemplateService, Depends(templates)]
TemplateCompilerServiceDependency = Annotated[TemplateCompilerService, Depends(compiler)]
