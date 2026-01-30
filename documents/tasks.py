import logging
import smtplib
import socket
import os
import tempfile
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail

from .models import Document, DocumentStatus
from .processing import apply_extracted_fields, get_keyword_map
from .services import process_document

logger = logging.getLogger(__name__)

PROCESSING_UPDATE_FIELDS = [
    "status",
    "processed_at",
    "error_message",
    "extracted_json",
    "extracted_text",
    "extracted_text_normalized",
    "text_content",
    "text_content_norm",
    "document_type",
    "contact_phone",
    "extracted_age_years",
    "extracted_experience_years",
    "ocr_used",
    "text_quality",
]

RETENTION_UPDATE_FIELDS = [
    "status",
    "is_deleted",
    "deleted_at",
    "deleted_reason",
]


def _iter_file_chunks(file_obj, chunk_size=1024 * 1024):
    if hasattr(file_obj, "chunks"):
        for chunk in file_obj.chunks(chunk_size=chunk_size):
            if chunk:
                yield chunk
        return
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk


def _prepare_document_file(doc):
    try:
        return doc.file.path, None
    except (AttributeError, NotImplementedError, ValueError):
        pass

    if not doc.file or not doc.file.name:
        raise FileNotFoundError("document file not available")

    file_name = doc.file.name
    suffix = os.path.splitext(file_name)[1]
    tmp_path = None
    file_obj = doc.file.storage.open(file_name, "rb")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_path = tmp_file.name
            for chunk in _iter_file_chunks(file_obj):
                tmp_file.write(chunk)
    except Exception:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
        raise
    finally:
        file_obj.close()

    def _cleanup():
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    return tmp_path, _cleanup


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_document_task(self, doc_id, *, force=False, force_ocr=False):
    try:
        with transaction.atomic():
            doc = Document.objects.select_for_update().get(id=doc_id)

            if doc.status == DocumentStatus.PROCESSING:
                logger.info("task_skip doc=%s reason=already_processing", doc_id)
                return {"skipped": True, "reason": "already_processing"}

            if doc.status == DocumentStatus.DONE and not force:
                logger.info("task_skip doc=%s reason=already_done", doc_id)
                return {"skipped": True, "reason": "already_done"}

            doc.mark_processing()
            doc.save(update_fields=PROCESSING_UPDATE_FIELDS)

            selected_fields = doc.selected_fields or []
            owner_id = doc.owner_id
            filename = doc.original_filename
    except Document.DoesNotExist:
        logger.warning("task_skip doc=%s reason=missing", doc_id)
        return {"skipped": True, "reason": "missing"}

    cleanup = None
    try:
        file_path, cleanup = _prepare_document_file(doc)
        keyword_map = get_keyword_map(owner_id, selected_fields)
        data, extracted_text, ocr_used, text_quality = process_document(
            file_path,
            selected_fields,
            keyword_map=keyword_map,
            doc_id=str(doc_id),
            filename=filename,
            force_ocr=force_ocr,
        )
    except Exception as exc:
        with transaction.atomic():
            updated = Document.objects.filter(id=doc_id).update(
                status=DocumentStatus.FAILED,
                processed_at=timezone.now(),
                error_message=(str(exc) or "")[:5000],
            )
        if not updated:
            logger.warning("process_failed doc=%s reason=missing", doc_id)
            return {"skipped": True, "reason": "missing"}
        logger.exception("process_failed doc=%s task=%s", doc_id, getattr(self.request, "id", "-"))
        raise
    finally:
        if cleanup:
            cleanup()

    with transaction.atomic():
        try:
            doc = Document.objects.select_for_update().get(id=doc_id)
        except Document.DoesNotExist:
            logger.warning("process_done doc=%s reason=missing", doc_id)
            return {"skipped": True, "reason": "missing"}
        apply_extracted_fields(doc, extracted_text, data)
        doc.mark_done(
            data,
            extracted_text=extracted_text,
            ocr_used=ocr_used,
            text_quality=text_quality,
        )
        doc.save()
        logger.info("process_done doc=%s task=%s", doc_id, getattr(self.request, "id", "-"))

    return {"ok": True}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def retention_cleanup_task(self, *, retention_days=30, reason="retention_30d"):
    cutoff = timezone.now() - timedelta(days=int(retention_days))
    docs = Document.objects.filter(uploaded_at__lt=cutoff, is_deleted=False).exclude(
        status=DocumentStatus.PROCESSING
    )
    total = 0
    deleted = 0
    for doc in docs.iterator():
        total += 1
        if doc.file and doc.file.name:
            try:
                doc.file.storage.delete(doc.file.name)
            except Exception:
                logger.exception("retention_delete_failed doc=%s", doc.id)
        doc.mark_deleted(reason=reason)
        doc.save(update_fields=RETENTION_UPDATE_FIELDS)
        deleted += 1
    logger.info(
        "retention_cleanup done total=%s deleted=%s cutoff=%s",
        total,
        deleted,
        cutoff.isoformat(),
    )
    return {"total": total, "deleted": deleted}


@shared_task(
    bind=True,
    autoretry_for=(smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, TimeoutError),
    retry_backoff=True,
    max_retries=3,
)
def send_email_task(self, *, subject: str, body: str, to_emails: list[str]):
    try:
        sent = send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=to_emails,
            fail_silently=False,
        )
        logger.info("email_sent subject=%s to=%s count=%s", subject, ",".join(to_emails), sent)
        return {"sent": sent}
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused) as exc:
        logger.error("email_send_rejected subject=%s to=%s error=%s", subject, ",".join(to_emails), exc)
        return {"sent": 0, "error": str(exc)}
    except Exception:
        logger.exception("email_send_failed subject=%s to=%s", subject, ",".join(to_emails))
        raise
