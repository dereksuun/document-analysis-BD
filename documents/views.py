import json
import os

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import get_valid_filename

from .forms import MultiUploadForm
from .models import Document, DocumentStatus
from .services import process_document

PAGE_SIZE = 10


@login_required
def upload_documents(request):
    if request.method == "POST":
        form = MultiUploadForm(request.POST, request.FILES)
        if form.is_valid():
            files = form.cleaned_data["files"]
            with transaction.atomic():
                for file_obj in files:
                    Document.objects.create(
                        owner=request.user,
                        file=file_obj,
                        original_filename=file_obj.name,
                    )
            return redirect("documents_list")
    else:
        form = MultiUploadForm()

    return render(request, "documents/upload.html", {"form": form})


@login_required
def documents_list(request):
    docs = (
        Document.objects.filter(owner=request.user)
        .order_by("-uploaded_at")
    )
    paginator = Paginator(docs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "documents/list.html", {"page_obj": page_obj})


@login_required
def process_document_view(request, doc_id):
    if request.method != "POST":
        return HttpResponseForbidden("Método inválido.")

    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    allow_reprocess = request.POST.get("reprocess") == "1"

    if doc.status == DocumentStatus.PROCESSING:
        return redirect("documents_list")
    if doc.status == DocumentStatus.DONE and not allow_reprocess:
        return redirect("documents_list")

    doc.mark_processing()
    doc.save(update_fields=["status", "processed_at", "error_message", "extracted_json"])

    try:
        data = process_document(doc.file.path)
        doc.mark_done(data)
        doc.save()
    except Exception as exc:
        doc.mark_failed(str(exc))
        doc.save(update_fields=["status", "processed_at", "error_message"])

    return redirect("documents_list")


@login_required
def download_document(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    filename = doc.original_filename or os.path.basename(doc.file.name)
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=filename)


def _build_json_filename(doc):
    base_name = doc.original_filename or str(doc.id)
    base_name = os.path.splitext(base_name)[0]
    safe_name = get_valid_filename(base_name) or str(doc.id)
    return f"{safe_name}.json"


@login_required
def download_document_json(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    json_data = doc.extracted_json or {}
    payload = json.dumps(json_data, ensure_ascii=False, indent=2)
    filename = _build_json_filename(doc)
    response = HttpResponse(payload, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def document_json_view(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id, owner=request.user)
    json_data = doc.extracted_json or {}
    return render(request, "documents/json.html", {"doc": doc, "json_data": json_data})
