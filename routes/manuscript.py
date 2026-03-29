"""
Manuscript export routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .auth_utils import require_auth
import manuscript as manuscript_module

router = APIRouter()


class ExportRequest(BaseModel):
    format: str = "docx"  # Single format (backward compat)
    font_name: str = "Times New Roman"
    font_size: int = 12
    double_spaced: bool = True
    include_title_page: bool = True


class PackageExportRequest(BaseModel):
    formats: list[str] = ["docx", "pdf", "epub", "txt", "odt", "kdp_proof_pdf"]
    font_name: str = "Times New Roman"
    font_size: int = 12
    double_spaced: bool = True
    include_title_page: bool = True


@router.get("/formats")
def get_formats(request: Request):
    """Get all available export formats."""
    require_auth(request)
    return {"formats": manuscript_module.get_available_formats()}


@router.post("/{book_id}/export")
def export_manuscript(request: Request, book_id: int, body: ExportRequest):
    """Export a book as a single manuscript format."""
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
            raise HTTPException(status_code=400, detail=f"Use /export-package for format: {body.format}")

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{book_id}/export-package")
def export_package(request: Request, book_id: int, body: PackageExportRequest):
    """
    Export a book as a multi-format package.
    Select formats via checkbox (e.g., ["docx", "pdf", "epub", "odt", "txt", "kdp_proof_pdf"]).
    """
    require_auth(request)

    try:
        result = manuscript_module.export_package(
            book_id=book_id,
            formats=body.formats,
            font_name=body.font_name,
            font_size=body.font_size,
            double_spaced=body.double_spaced,
            include_title_page=body.include_title_page,
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{book_id}/export/{filename:path}")
def download_manuscript(request: Request, book_id: int, filename: str):
    """Download an exported manuscript file (supports nested paths for packages)."""
    require_auth(request)

    file_path = manuscript_module.MANUSCRIPT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Manuscript not found")

    # Ensure path is within MANUSCRIPT_DIR
    try:
        file_path.resolve().relative_to(manuscript_module.MANUSCRIPT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    media_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".odt": "application/vnd.oasis.opendocument.text",
        ".epub": "application/epub+zip",
    }
    media_type = media_types.get(file_path.suffix, "application/octet-stream")

    return FileResponse(str(file_path), media_type=media_type, filename=file_path.name)


@router.get("/{book_id}/manuscripts")
def list_manuscripts(request: Request, book_id: int):
    """List all exported manuscripts for a book."""
    require_auth(request)
    manuscripts = manuscript_module.list_manuscripts(book_id)
    return {"manuscripts": manuscripts}


@router.delete("/{book_id}/manuscripts/{filename}")
def delete_manuscript(request: Request, book_id: int, filename: str):
    """Delete an exported manuscript or package."""
    require_auth(request)
    success = manuscript_module.delete_manuscript(filename)
    if not success:
        raise HTTPException(status_code=404, detail="Manuscript not found")
    return {"status": "deleted"}
