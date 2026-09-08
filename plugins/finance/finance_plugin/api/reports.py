from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from finance_plugin.dependencies import (
    ReportServiceDependency,
    TemplateCompilerServiceDependency,
    TextTemplateServiceDependency,
)
from finance_plugin.schemas.report import (
    ReportCompileCreate,
    ReportCreate,
    ReportRead,
    ReportSource,
    ReportUpdate,
)
from plugin_runtime.errors import ApiError

router = APIRouter(prefix="/reports", tags=["reports"])

_MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2 MB


@router.get("", response_model=list[ReportRead])
def list_reports(
    service: ReportServiceDependency,
    ticker: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    review_type: Annotated[str | None, Query(alias="reviewType")] = None,
    source: Annotated[ReportSource | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReportRead]:
    return service.list_reports(
        ticker=ticker,
        tag=tag,
        review_type=review_type,
        source=source,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    service: ReportServiceDependency,
) -> ReportRead:
    return service.create_external_report(
        content=payload.content,
        name=payload.name,
        slug=payload.slug,
        metadata=payload.metadata,
    )


@router.post(
    "/compile/{template_id}", response_model=ReportRead, status_code=status.HTTP_201_CREATED
)
def compile_report(
    template_id: int,
    report_service: ReportServiceDependency,
    template_service: TextTemplateServiceDependency,
    compiler_service: TemplateCompilerServiceDependency,
    payload: ReportCompileCreate | None = None,
) -> ReportRead:
    template = template_service.get_template_model(template_id)
    compiled = compiler_service.compile(
        template.content, inputs=payload.inputs if payload else None
    )
    metadata = payload.metadata if payload is not None else None
    return report_service.create_from_template(template, compiled, metadata=metadata)


@router.post("/upload", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def upload_report(
    service: ReportServiceDependency,
    file: Annotated[UploadFile, File(description="Markdown file (.md)")],
    slug: Annotated[str | None, Form()] = None,
    author: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form(description="Comma-separated tags")] = None,
) -> ReportRead:
    filename = file.filename or "report.md"
    if not filename.lower().endswith(".md"):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_file_type",
            message="Only markdown (.md) files are accepted",
        )

    if file.content_type and file.content_type not in (
        "text/markdown",
        "text/plain",
        "text/x-markdown",
        "application/octet-stream",
    ):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_file_type",
            message="Only markdown (.md) files are accepted",
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_SIZE:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="file_too_large",
            message="File must be smaller than 2 MB",
        )

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_file_encoding",
            message="Uploaded markdown must be UTF-8 encoded",
        ) from exc

    if not content.strip():
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="empty_file",
            message="Uploaded file is empty",
        )

    if filename.lower().endswith(".md"):
        filename = filename[:-3]

    resolved_slug = slug.strip() if slug and slug.strip() else filename

    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    metadata = {
        "author": author.strip() if author and author.strip() else None,
        "description": description.strip() if description and description.strip() else None,
        "tags": parsed_tags,
    }

    return service.create_from_upload(
        content=content,
        slug=resolved_slug,
        name=filename,
        metadata=metadata,
    )


@router.get("/{slug}", response_model=ReportRead)
def get_report(
    slug: str,
    service: ReportServiceDependency,
) -> ReportRead:
    return service.get_report_by_slug(slug)


@router.patch("/{slug}", response_model=ReportRead)
def update_report(
    slug: str,
    payload: ReportUpdate,
    service: ReportServiceDependency,
) -> ReportRead:
    return service.update_report_by_slug(slug, payload)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    slug: str,
    service: ReportServiceDependency,
) -> Response:
    service.delete_report_by_slug(slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{slug}/download")
def download_report(
    slug: str,
    service: ReportServiceDependency,
) -> Response:
    report = service.get_report_model_by_slug(slug)
    return Response(
        content=report.content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{report.slug}.md"',
        },
    )
