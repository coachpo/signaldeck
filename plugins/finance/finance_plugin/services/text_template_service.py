from __future__ import annotations

from finance_plugin.models.text_template import TextTemplate
from finance_plugin.repositories.text_template import TextTemplateRepository
from finance_plugin.schemas.text_template import (
    TextTemplateCreate,
    TextTemplateRead,
    TextTemplateUpdate,
)
from plugin_runtime.db_errors import is_unique_constraint_violation
from plugin_runtime.errors import business_rule_error, not_found_error
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_TEXT_TEMPLATE_NAME_CONSTRAINTS = frozenset({"uq_text_templates_name"})


class TextTemplateService:
    session: Session
    repository: TextTemplateRepository

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TextTemplateRepository(session)

    def list_templates(self) -> list[TextTemplateRead]:
        templates = self.repository.list_all()
        return [TextTemplateRead.model_validate(t) for t in templates]

    def get_template(self, template_id: int) -> TextTemplateRead:
        template = self._get_model(template_id)
        return TextTemplateRead.model_validate(template)

    def get_template_model(self, template_id: int) -> TextTemplate:
        return self._get_model(template_id)

    def create_template(self, payload: TextTemplateCreate) -> TextTemplateRead:
        if self.repository.get_by_name(payload.name) is not None:
            raise self._duplicate_name_error()
        template = TextTemplate(
            name=payload.name,
            content=payload.content,
        )
        _ = self.repository.add(template)
        try:
            self.session.commit()
            self.session.refresh(template)
        except IntegrityError as exc:
            self.session.rollback()
            if is_unique_constraint_violation(exc, _TEXT_TEMPLATE_NAME_CONSTRAINTS):
                raise self._duplicate_name_error() from exc
            raise
        except Exception:
            self.session.rollback()
            raise
        return TextTemplateRead.model_validate(template)

    def update_template(self, template_id: int, payload: TextTemplateUpdate) -> TextTemplateRead:
        template = self._get_model(template_id)
        if payload.name is not None and payload.name != template.name:
            duplicate = self.repository.get_by_name(payload.name)
            if duplicate is not None and duplicate.id != template.id:
                raise business_rule_error(
                    "duplicate_template_name",
                    "A template with this name already exists",
                )
            template.name = payload.name
        if payload.content is not None:
            template.content = payload.content
        self.session.commit()
        self.session.refresh(template)
        return TextTemplateRead.model_validate(template)

    def delete_template(self, template_id: int) -> None:
        template = self._get_model(template_id)
        self.repository.delete(template)
        self.session.commit()

    @staticmethod
    def _duplicate_name_error() -> Exception:
        return business_rule_error(
            "duplicate_template_name",
            "A template with this name already exists",
        )

    def _get_model(self, template_id: int) -> TextTemplate:
        template = self.repository.get(template_id)
        if template is None:
            raise not_found_error("TextTemplate")
        return template
