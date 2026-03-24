"""
Manuscript export routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel
from pathlib import Path
from .auth_utils import require_auth
import manuscript as manuscript_module

router = APIRouter()


class ExportRequest(BaseModel):
    format: str = "docx"  # docx, txt
    font_name: str = "Times New Roman"
    font_size: int = 12
    double_spaced: bool = True
    include_title_page: bool = True


@router.post("/{book_id}/export")
def export_manuscript(request: Request, book_id: int, body: ExportRequest):
    """Export a book as a submission-ready manuscript."""
    require_auth(request)

    try:
        if body.format == "docx":
            result = manuscript_module.export_manuscript_docx(
                book_id=book_id,
                font_name=body.font_name,
                font_size=body.font_size,
                double_spaced=body.double_spaced,
                include_title_page=body.include_title_page,
            )
        elif body.format == "txt":
            result = manuscript_module.export_manuscript_txt(book_id=book_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {body.format}")

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{book_id}/export/{filename}")
def download_manuscript(request: Request, book_id: int, filename: str):
    """Download an exported manuscript file."""
    require_auth(request)

    file_path = manuscript_module.MANUSCRIPT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Manuscript not found")

    media_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
    }
    media_type = media_types.get(file_path.suffix, "application/octet-stream")

    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=filename,
    )


@router.get("/{book_id}/manuscripts")
def list_manuscripts(request: Request, book_id: int):
    """List all exported manuscripts for a book."""
    require_auth(request)
    manuscripts = manuscript_module.list_manuscripts(book_id)
    return {"manuscripts": manuscripts}


@router.delete("/{book_id}/manuscripts/{filename}")
def delete_manuscript(request: Request, book_id: int, filename: str):
    """Delete an exported manuscript."""
    require_auth(request)
    success = manuscript_module.delete_manuscript(filename)
    if not success:
        raise HTTPException(status_code=404, detail="Manuscript not found")
    return {"status": "deleted"}
