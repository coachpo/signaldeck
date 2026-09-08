from __future__ import annotations

from fastapi import APIRouter, Response, status
from finance_plugin.dependencies import (
    TemplateCompilerServiceDependency,
    TextTemplateServiceDependency,
)
from finance_plugin.schemas.text_template import (
    PlaceholderTreeRead,
    TextTemplateCompileRead,
    TextTemplateCreate,
    TextTemplateInlineCompile,
    TextTemplateInlineCompileRead,
    TextTemplateRead,
    TextTemplateStoredCompile,
    TextTemplateUpdate,
)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TextTemplateRead])
def list_templates(
    service: TextTemplateServiceDependency,
) -> list[TextTemplateRead]:
    return service.list_templates()


@router.post("", response_model=TextTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TextTemplateCreate,
    service: TextTemplateServiceDependency,
) -> TextTemplateRead:
    return service.create_template(payload)


@router.get("/placeholders", response_model=PlaceholderTreeRead)
def get_placeholders(
    compiler_service: TemplateCompilerServiceDependency,
) -> PlaceholderTreeRead:
    tree = compiler_service.get_placeholder_tree()
    return PlaceholderTreeRead.model_validate(tree)


@router.post("/compile", response_model=TextTemplateInlineCompileRead)
def compile_inline(
    payload: TextTemplateInlineCompile,
    compiler_service: TemplateCompilerServiceDependency,
) -> TextTemplateInlineCompileRead:
    compiled = compiler_service.compile(payload.content, inputs=payload.inputs)
    return TextTemplateInlineCompileRead.model_validate({"compiled": compiled})


@router.get("/{template_id:int}", response_model=TextTemplateRead)
def get_template(
    template_id: int,
    service: TextTemplateServiceDependency,
) -> TextTemplateRead:
    return service.get_template(template_id)


@router.patch("/{template_id:int}", response_model=TextTemplateRead)
def update_template(
    template_id: int,
    payload: TextTemplateUpdate,
    service: TextTemplateServiceDependency,
) -> TextTemplateRead:
    return service.update_template(template_id, payload)


@router.delete("/{template_id:int}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    service: TextTemplateServiceDependency,
) -> Response:
    service.delete_template(template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{template_id:int}/compile", response_model=TextTemplateCompileRead)
def compile_template(
    template_id: int,
    template_service: TextTemplateServiceDependency,
    compiler_service: TemplateCompilerServiceDependency,
) -> TextTemplateCompileRead:
    template = template_service.get_template_model(template_id)
    compiled = compiler_service.compile(template.content)
    return TextTemplateCompileRead.model_validate(
        {
            "id": template.id,
            "name": template.name,
            "compiled": compiled,
        }
    )


@router.post("/{template_id:int}/compile", response_model=TextTemplateCompileRead)
def compile_template_with_inputs(
    template_id: int,
    payload: TextTemplateStoredCompile,
    template_service: TextTemplateServiceDependency,
    compiler_service: TemplateCompilerServiceDependency,
) -> TextTemplateCompileRead:
    template = template_service.get_template_model(template_id)
    compiled = compiler_service.compile(template.content, inputs=payload.inputs)
    return TextTemplateCompileRead.model_validate(
        {
            "id": template.id,
            "name": template.name,
            "compiled": compiled,
        }
    )
