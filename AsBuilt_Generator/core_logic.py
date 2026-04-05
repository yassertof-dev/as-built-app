"""
AsBuilt Drawings Generator - Core Logic Module
Handles counter management, text processing, PDF creation, and file operations.
"""

import os
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

from docxtpl import DocxTemplate
from pypdf import PdfWriter, PdfReader


class DataManager:
    """Manages counters and history storage."""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.counters_file = self.base_path / "counters.json"
        self.history_file = self.base_path / "history.json"
        self.counters = self._load_counters()
        self.history = self._load_history()
    
    def _load_counters(self) -> Dict[str, int]:
        """Load counters from JSON file or create default."""
        default_counters = {"AR": 0, "CV": 0, "MECH": 0, "ELEC": 0}
        if self.counters_file.exists():
            try:
                with open(self.counters_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return default_counters
        return default_counters
    
    def _load_history(self) -> List[Dict]:
        """Load history from JSON file or create empty list."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []
    
    def save_counters(self):
        """Save current counters to JSON file."""
        with open(self.counters_file, 'w', encoding='utf-8') as f:
            json.dump(self.counters, f, ensure_ascii=False, indent=2)
    
    def save_history(self):
        """Save history to JSON file."""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
    
    def get_next_serial(self, discipline: str) -> int:
        """Get the next serial number for a discipline (peek without incrementing)."""
        return self.counters.get(discipline, 0) + 1
    
    def update_counter(self, discipline: str, final_serial: int):
        """Update the counter for a discipline to the last used serial."""
        self.counters[discipline] = final_serial
        self.save_counters()
    
    def add_history(self, plot_number: str, discipline: str, discipline_name: str,
                   serial: int, description: str, pdf_path: str, date: str):
        """Add an entry to the history."""
        entry = {
            "plot_number": plot_number,
            "discipline": discipline,
            "discipline_name": discipline_name,
            "serial": serial,
            "description": description,
            "pdf_path": pdf_path,
            "date": date,
            "timestamp": datetime.now().isoformat()
        }
        self.history.append(entry)
        self.save_history()


class TextProcessor:
    """Handles text parsing and validation for plot numbers."""
    
    # Allowed separators: / * - . space = , ، ’
    SEPARATOR_PATTERN = r'[/\*\-\. =,،’]+'
    
    @staticmethod
    def parse_plot_numbers(text: str) -> List[str]:
        """Parse plot numbers from input text, splitting by allowed separators."""
        if not text.strip():
            return []
        
        # Split by separators and filter empty strings
        parts = re.split(TextProcessor.SEPARATOR_PATTERN, text.strip())
        return [p.strip() for p in parts if p.strip()]
    
    @staticmethod
    def validate_plot_numbers(text: str) -> Tuple[bool, List[str]]:
        """
        Validate plot numbers input.
        Returns (is_valid, error_messages)
        """
        if not text.strip():
            return False, ["حقل أرقام القطع لا يمكن أن يكون فارغاً"]
        
        # Check for invalid characters (only digits and allowed separators)
        allowed_pattern = r'^[\d/\*\-\. =,،’\s]+$'
        if not re.match(allowed_pattern, text):
            return False, ["يحتوي الحقل على أحرف غير مسموحة. استخدم الأرقام والفواصل فقط"]
        
        plot_numbers = TextProcessor.parse_plot_numbers(text)
        if not plot_numbers:
            return False, ["لم يتم العثور على أرقام قطع صالحة"]
        
        return True, []
    
    @staticmethod
    def format_serial(serial: int) -> str:
        """Format serial number: 3 digits for <1000, as-is for >=1000."""
        if serial < 1000:
            return f"{serial:03d}"
        return str(serial)


class PDFCreator:
    """Handles DOCX to PDF conversion and merging."""
    
    DISCIPLINE_CODES = {
        "معماري": "AR",
        "مدني": "CV",
        "ميكانيكا": "MECH",
        "كهرباء": "ELEC"
    }
    
    DISCIPLINE_SHAPES = {
        "AR": "معماري",
        "CV": "مدني",
        "MECH": "ميكانيكا",
        "ELEC": "كهرباء"
    }
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.templates_dir = self.base_path / "templates"
        self.output_dir = self.base_path / "OUTPUT"
        
        # Ensure output directories exist
        for disc_name in ["معماري", "مدني", "ميكانيكا", "كهرباء"]:
            (self.output_dir / disc_name).mkdir(parents=True, exist_ok=True)
    
    def fill_template(self, template_path: Path, data: Dict[str, Any], 
                     output_docx: Path) -> bool:
        """Fill a Word template with data using docxtpl."""
        try:
            tpl = DocxTemplate(str(template_path))
            tpl.render(data)
            tpl.save(str(output_docx))
            return True
        except Exception as e:
            print(f"Error filling template: {e}")
            return False
    
    def convert_docx_to_pdf(self, docx_path: Path, pdf_path: Path) -> bool:
        """Convert DOCX to PDF using LibreOffice or docx2pdf."""
        try:
            # Try LibreOffice first (preferred, cross-platform)
            soffice_cmd = None
            
            # Check common paths for soffice
            possible_paths = [
                "soffice",  # Linux/Mac in PATH
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
            ]
            
            for path in possible_paths:
                try:
                    result = subprocess.run(
                        [path, "--headless", "--convert-to", "pdf", 
                         "--outdir", str(pdf_path.parent), str(docx_path)],
                        capture_output=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        # LibreOffice creates PDF with same name as DOCX
                        expected_pdf = pdf_path.parent / docx_path.stem.replace('.docx', '') / '.pdf'
                        if not expected_pdf.exists():
                            # Try direct name match
                            expected_pdf = pdf_path.parent / f"{docx_path.stem}.pdf"
                        
                        if expected_pdf.exists() and expected_pdf != pdf_path:
                            shutil.move(str(expected_pdf), str(pdf_path))
                        return True
                    soffice_cmd = path
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            
            # If LibreOffice not found, try docx2pdf (requires MS Word on Windows)
            try:
                from docx2pdf import convert
                convert(str(docx_path), str(pdf_path))
                return True
            except ImportError:
                pass
            except Exception:
                pass
            
            print("لا يوجد LibreOffice أو Microsoft Word مثبت للتحويل إلى PDF")
            return False
            
        except Exception as e:
            print(f"Conversion error: {e}")
            return False
    
    def merge_pdfs(self, main_pdf: Path, attachments: List[Path], output_pdf: Path) -> bool:
        """Merge main PDF with attachment PDFs."""
        try:
            writer = PdfWriter()
            
            # Add main PDF pages
            if main_pdf.exists():
                reader = PdfReader(str(main_pdf))
                for page in reader.pages:
                    writer.add_page(page)
            
            # Add attachment PDFs in order
            for attachment in attachments:
                if attachment.exists():
                    reader = PdfReader(str(attachment))
                    for page in reader.pages:
                        writer.add_page(page)
            
            # Write merged PDF
            with open(output_pdf, 'wb') as f:
                writer.write(f)
            
            return True
            
        except Exception as e:
            print(f"Merge error: {e}")
            return False
    
    def create_pdf(self, discipline: str, discipline_name: str, plot_number: str,
                  date_str: str, description: str, serial: int,
                  attachments: List[Path]) -> Tuple[bool, str, Optional[str]]:
        """
        Create a single PDF for a plot.
        Returns: (success, message, pdf_path_or_error)
        """
        try:
            disc_code = self.DISCIPLINE_CODES.get(discipline, discipline)
            formatted_serial = TextProcessor.format_serial(serial)
            
            # Generate filename
            filename = f"TOL-ADW-DOC-ASB-{disc_code}-{formatted_serial}.pdf"
            output_folder = self.output_dir / discipline_name
            output_folder.mkdir(parents=True, exist_ok=True)
            final_pdf = output_folder / filename
            
            # Template path
            template_name = f"template_{disc_code}.docx"
            template_path = self.templates_dir / template_name
            
            if not template_path.exists():
                return False, f"القالب {template_name} غير موجود", None
            
            # Prepare data for template
            data = {
                "PLOT_NUMBER": plot_number,
                "DATE": date_str,
                "DESCRIPTION": description,
                "SERIAL_NUMBER": formatted_serial,
                "DISCIPLINE_SHAPE": self.DISCIPLINE_SHAPES.get(disc_code, discipline_name)
            }
            
            # Create temporary DOCX
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
                temp_docx = Path(tmp.name)
            
            # Fill template
            if not self.fill_template(template_path, data, temp_docx):
                return False, "فشل ملء القالب", None
            
            # Convert to temporary PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                temp_pdf = Path(tmp.name)
            
            if not self.convert_docx_to_pdf(temp_docx, temp_pdf):
                temp_docx.unlink(missing_ok=True)
                temp_pdf.unlink(missing_ok=True)
                return False, "فشل تحويل DOCX إلى PDF (تأكد من تثبيت LibreOffice)", None
            
            # Merge with attachments if any
            if attachments:
                if not self.merge_pdfs(temp_pdf, attachments, final_pdf):
                    temp_docx.unlink(missing_ok=True)
                    temp_pdf.unlink(missing_ok=True)
                    return False, "فشل دمج المرفقات", None
            else:
                # Just move the converted PDF
                shutil.move(str(temp_pdf), str(final_pdf))
            
            # Cleanup temp files
            temp_docx.unlink(missing_ok=True)
            if temp_pdf.exists():
                temp_pdf.unlink(missing_ok=True)
            
            return True, f"تم إنشاء {filename}", str(final_pdf)
            
        except Exception as e:
            return False, f"خطأ غير متوقع: {str(e)}", None
