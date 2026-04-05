"""
AsBuilt Drawings Generator - UI Design Module
PyQt6-based user interface with RTL support, tabs for 4 disciplines,
progress tracking, and file management.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QLabel, QLineEdit, QTextEdit, QDateEdit, QPushButton,
    QListWidget, QListWidgetItem, QProgressBar, QStatusBar, QFormLayout,
    QFileDialog, QMessageBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QPalette

from core_logic import DataManager, TextProcessor, PDFCreator


class SerialSpinBox(QLineEdit):
    """Custom line edit that displays serial numbers with leading zeros."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("001")
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFont(QFont("Segoe UI", 11))
        
    def set_value(self, value: int):
        """Set the serial number value with proper formatting."""
        if value < 1000:
            self.setText(f"{value:03d}")
        else:
            self.setText(str(value))
    
    def get_value(self) -> int:
        """Get the integer value from the text."""
        try:
            return int(self.text().lstrip('0') or '0')
        except ValueError:
            return 1


class PDFWorker(QObject):
    """Worker thread for PDF generation to avoid UI freezing."""
    
    progress = pyqtSignal(int, int)  # current, total
    file_done = pyqtSignal(str, str, str)  # plot_number, full_serial, pdf_path
    finished = pyqtSignal(int, list)  # success_count, errors
    
    def __init__(self, pdf_creator: PDFCreator, data_manager: DataManager,
                 discipline_code: str, discipline_name: str,
                 plot_numbers: List[str], date_str: str, description: str,
                 start_serial: int, attachments: List[Path]):
        super().__init__()
        self.pdf_creator = pdf_creator
        self.data_manager = data_manager
        self.discipline_code = discipline_code
        self.discipline_name = discipline_name
        self.plot_numbers = plot_numbers
        self.date_str = date_str
        self.description = description
        self.start_serial = start_serial
        self.attachments = attachments
    
    def run(self):
        """Execute PDF generation in background."""
        success_count = 0
        errors = []
        last_successful_serial = self.start_serial - 1
        
        for i, plot_number in enumerate(self.plot_numbers):
            current_serial = self.start_serial + i
            
            success, message, result = self.pdf_creator.create_pdf(
                discipline=self.discipline_code,
                discipline_name=self.discipline_name,
                plot_number=plot_number,
                date_str=self.date_str,
                description=self.description,
                serial=current_serial,
                attachments=self.attachments
            )
            
            if success:
                success_count += 1
                last_successful_serial = current_serial
                formatted_serial = TextProcessor.format_serial(current_serial)
                full_serial = f"TOL-ADW-DOC-ASB-{self.discipline_code}-{formatted_serial}"
                
                # Add to history
                self.data_manager.add_history(
                    plot_number=plot_number,
                    discipline=self.discipline_code,
                    discipline_name=self.discipline_name,
                    serial=current_serial,
                    description=self.description,
                    pdf_path=result,
                    date=self.date_str
                )
                
                self.file_done.emit(plot_number, full_serial, result)
            else:
                errors.append(f"القطعة {plot_number}: {message}")
            
            # Emit progress
            self.progress.emit(i + 1, len(self.plot_numbers))
        
        # Update counter to last successful serial
        if last_successful_serial >= self.start_serial:
            self.data_manager.update_counter(self.discipline_code, last_successful_serial)
        
        self.finished.emit(success_count, errors)


class DisciplineTab(QWidget):
    """Widget for a single discipline tab."""
    
    def __init__(self, discipline_name: str, discipline_code: str, 
                 data_manager: DataManager, pdf_creator: PDFCreator, parent=None):
        super().__init__(parent)
        self.discipline_name = discipline_name
        self.discipline_code = discipline_code
        self.data_manager = data_manager
        self.pdf_creator = pdf_creator
        self.attachments = []
        
        self._setup_ui()
        self._load_initial_serial()
    
    def _setup_ui(self):
        """Setup the UI components for this tab."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Data Group
        data_group = QGroupBox("بيانات المخطط")
        data_layout = QFormLayout()
        data_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        data_layout.setFormAlignment(Qt.AlignmentFlag.AlignRight)
        data_layout.setSpacing(10)
        
        # Plot Number Field
        self.plot_input = QLineEdit()
        self.plot_input.setPlaceholderText("مثال: 102030/102031/102032 أو 1-2-3")
        self.plot_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.plot_input.setFont(QFont("Segoe UI", 11))
        self.plot_input.textChanged.connect(self._validate_plot_input)
        data_layout.addRow("رقم القطعة:", self.plot_input)
        
        # Date Field
        self.date_input = QDateEdit()
        self.date_input.setDate(datetime.now())
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        self.date_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date_input.setFont(QFont("Segoe UI", 11))
        self.date_input.setCalendarPopup(True)
        data_layout.addRow("التاريخ:", self.date_input)
        
        # Description Field
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("وصف المخطط (اختياري)")
        self.desc_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.desc_input.setFont(QFont("Segoe UI", 11))
        self.desc_input.setMaximumHeight(80)
        data_layout.addRow("الوصف:", self.desc_input)
        
        # Serial Number Field
        self.serial_input = SerialSpinBox()
        data_layout.addRow("الرقم التسلسلي:", self.serial_input)
        
        data_group.setLayout(data_layout)
        main_layout.addWidget(data_group)
        
        # Attachments Group
        attach_group = QGroupBox("الملفات المرفقة (PDF)")
        attach_layout = QVBoxLayout()
        attach_layout.setSpacing(10)
        
        self.attach_list = QListWidget()
        self.attach_list.setFont(QFont("Segoe UI", 10))
        self.attach_list.setMaximumHeight(100)
        attach_layout.addWidget(self.attach_list)
        
        # Attachment buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.add_attach_btn = QPushButton("➕ إضافة ملف PDF")
        self.add_attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        self.add_attach_btn.clicked.connect(self._add_attachment)
        btn_layout.addWidget(self.add_attach_btn)
        
        self.remove_attach_btn = QPushButton("➖ إزالة المحدد")
        self.remove_attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.remove_attach_btn.clicked.connect(self._remove_attachment)
        btn_layout.addWidget(self.remove_attach_btn)
        
        btn_layout.addStretch()
        attach_layout.addLayout(btn_layout)
        attach_group.setLayout(attach_layout)
        main_layout.addWidget(attach_group)
        
        # Create Button
        self.create_btn = QPushButton("📄 إنشاء PDF")
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.create_btn.clicked.connect(self._start_creation)
        main_layout.addWidget(self.create_btn)
        
        main_layout.addStretch()
        self.setLayout(main_layout)
    
    def _load_initial_serial(self):
        """Load the initial serial number from data manager."""
        next_serial = self.data_manager.get_next_serial(self.discipline_code)
        self.serial_input.set_value(next_serial)
    
    def _validate_plot_input(self):
        """Validate plot number input in real-time."""
        text = self.plot_input.text()
        is_valid, _ = TextProcessor.validate_plot_numbers(text)
        
        if not is_valid and text.strip():
            # Check if it's just invalid characters
            allowed_pattern = r'^[\d/\*\-\. =,،’\s]+$'
            if not re.match(allowed_pattern, text):
                self.plot_input.setStyleSheet("background-color: #ffcccc;")
            else:
                self.plot_input.setStyleSheet("")
        else:
            self.plot_input.setStyleSheet("")
    
    def _add_attachment(self):
        """Add PDF attachment(s)."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "إضافة ملفات PDF", "", "PDF Files (*.pdf)"
        )
        
        for file_path in files:
            if file_path not in self.attachments:
                self.attachments.append(Path(file_path))
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                self.attach_list.addItem(item)
    
    def _remove_attachment(self):
        """Remove selected attachment."""
        current_row = self.attach_list.currentRow()
        if current_row >= 0:
            item = self.attach_list.takeItem(current_row)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.attachments = [p for p in self.attachments if str(p) != file_path]
    
    def _start_creation(self):
        """Start PDF creation process."""
        # Validate input
        plot_text = self.plot_input.text()
        is_valid, errors = TextProcessor.validate_plot_numbers(plot_text)
        
        if not is_valid:
            QMessageBox.warning(self, "خطأ في الإدخال", "\n".join(errors))
            return
        
        plot_numbers = TextProcessor.parse_plot_numbers(plot_text)
        date_str = self.date_input.date().toString("yyyy-MM-dd")
        description = self.desc_input.toPlainText().strip()
        start_serial = self.serial_input.get_value()
        
        if start_serial < 1:
            QMessageBox.warning(self, "خطأ", "الرقم التسلسلي يجب أن يكون أكبر من 0")
            return
        
        # Disable button and emit signal to start worker
        self.create_btn.setEnabled(False)
        self.create_btn.setText("⏳ جاري العمل...")
        
        # Emit signal to main window to start worker thread
        if hasattr(self.parent(), 'start_pdf_generation'):
            self.parent().start_pdf_generation(
                discipline_code=self.discipline_code,
                discipline_name=self.discipline_name,
                plot_numbers=plot_numbers,
                date_str=date_str,
                description=description,
                start_serial=start_serial,
                attachments=self.attachments.copy()
            )
    
    def reset_button(self):
        """Reset the create button after completion."""
        self.create_btn.setEnabled(True)
        self.create_btn.setText("📄 إنشاء PDF")
        # Update serial for next use
        self._load_initial_serial()


class AsBuiltGeneratorWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Setup paths
        self.base_path = Path(__file__).parent.absolute()
        self.data_manager = DataManager(str(self.base_path))
        self.pdf_creator = PDFCreator(str(self.base_path))
        
        # Worker thread reference
        self.worker_thread = None
        self.worker = None
        
        self._setup_ui()
        self._check_templates()
    
    def _setup_ui(self):
        """Setup the main UI."""
        self.setWindowTitle("AsBuilt Drawings Generator")
        self.setMinimumSize(1100, 750)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        # Central widget
        central_widget = QWidget()
        central_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        central_widget.setLayout(main_layout)
        
        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tabs.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        
        # Style tabs
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #bdc3c7;
                border-radius: 4px;
                background: white;
            }
            QTabBar::tab {
                background: #ecf0f1;
                color: #2c3e50;
                padding: 12px 24px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #3498db;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #bdc3c7;
            }
        """)
        
        # Create discipline tabs
        disciplines = [
            ("معماري", "AR"),
            ("مدني", "CV"),
            ("ميكانيكا", "MECH"),
            ("كهرباء", "ELEC")
        ]
        
        self.tab_widgets = {}
        for disc_name, disc_code in disciplines:
            tab = DisciplineTab(disc_name, disc_code, self.data_manager, 
                               self.pdf_creator, self)
            self.tab_widgets[disc_code] = tab
            self.tabs.addTab(tab, disc_name)
        
        main_layout.addWidget(self.tabs)
        
        # Progress Section
        progress_frame = QFrame()
        progress_frame.setStyleSheet("background: white; border: 1px solid #bdc3c7; border-radius: 4px;")
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(10)
        progress_layout.setContentsMargins(15, 15, 15, 15)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3498db;
                border-radius: 4px;
                background: white;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #2ecc71;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        # Log list
        self.log_label = QLabel("سجل الملفات المنجزة:")
        self.log_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        progress_layout.addWidget(self.log_label)
        
        self.log_list = QListWidget()
        self.log_list.setFont(QFont("Segoe UI", 10))
        self.log_list.setMaximumHeight(150)
        progress_layout.addWidget(self.log_list)
        
        progress_frame.setLayout(progress_layout)
        main_layout.addWidget(progress_frame)
        
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("جاهز")
        self.status_bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        # Set global style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ecf0f1;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit, QTextEdit, QDateEdit {
                border: 2px solid #bdc3c7;
                border-radius: 4px;
                padding: 6px;
                background: white;
            }
            QLineEdit:focus, QTextEdit:focus, QDateEdit:focus {
                border-color: #3498db;
            }
        """)
    
    def _check_templates(self):
        """Check if template files exist, create placeholders if not."""
        templates_needed = {
            "template_AR.docx": "معماري",
            "template_CV.docx": "مدني",
            "template_MECH.docx": "ميكانيكا",
            "template_ELEC.docx": "كهرباء"
        }
        
        missing = []
        for filename, disc_name in templates_needed.items():
            template_path = self.base_path / "templates" / filename
            if not template_path.exists():
                missing.append(f"{filename} ({disc_name})")
        
        if missing:
            QMessageBox.warning(
                self, "قوالب مفقودة",
                f"القوالب التالية غير موجودة في مجلد templates:\n\n" +
                "\n".join(missing) +
                "\n\nيرجى إضافتها قبل استخدام البرنامج."
            )
    
    def start_pdf_generation(self, discipline_code: str, discipline_name: str,
                            plot_numbers: List[str], date_str: str,
                            description: str, start_serial: int,
                            attachments: List[Path]):
        """Start PDF generation in a background thread."""
        # Clear log
        self.log_list.clear()
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(plot_numbers))
        self.progress_bar.setValue(0)
        
        # Create worker and thread
        self.worker_thread = QThread()
        self.worker = PDFWorker(
            pdf_creator=self.pdf_creator,
            data_manager=self.data_manager,
            discipline_code=discipline_code,
            discipline_name=discipline_name,
            plot_numbers=plot_numbers,
            date_str=date_str,
            description=description,
            start_serial=start_serial,
            attachments=attachments
        )
        
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals
        self.worker.progress.connect(self._update_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished.connect(self._on_generation_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        
        # Start thread
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()
    
    def _update_progress(self, current: int, total: int):
        """Update progress bar and status."""
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(f"جاري إنشاء الملفات: {current}/{total}")
    
    def _on_file_done(self, plot_number: str, full_serial: str, pdf_path: str):
        """Handle completion of a single file."""
        item = QListWidgetItem(f"✅ القطعة {plot_number} → {full_serial}.pdf")
        item.setForeground(QColor("#27ae60"))
        self.log_list.addItem(item)
        # Auto-scroll to bottom
        self.log_list.scrollToBottom()
    
    def _on_generation_finished(self, success_count: int, errors: list):
        """Handle completion of all files."""
        # Reset button in active tab
        current_tab = self.tabs.currentWidget()
        if isinstance(current_tab, DisciplineTab):
            current_tab.reset_button()
        
        # Hide progress bar
        self.progress_bar.setVisible(False)
        
        # Show results
        if errors:
            error_msg = f"تم إنشاء {success_count} ملف بنجاح.\n\nأخطاء:\n" + "\n".join(errors)
            QMessageBox.warning(self, "اكتمل مع أخطاء", error_msg)
        else:
            QMessageBox.information(
                self, "تم بنجاح",
                f"تم إنشاء {success_count} ملف PDF بنجاح!\n\n" +
                f"المسار: {self.base_path / 'OUTPUT'}"
            )
        
        self.status_bar.showMessage("جاهز")
        
        # Offer to open output folder
        if success_count > 0:
            reply = QMessageBox.question(
                self, "فتح المجلد",
                "هل تريد فتح مجلد الإخراج؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                current_disc = self.tabs.currentWidget().discipline_name
                output_path = self.base_path / "OUTPUT" / current_disc
                os.startfile(str(output_path)) if os.name == 'nt' else \
                    os.system(f"xdg-open '{output_path}'")


# Import re for validation
import re
from PyQt6.QtCore import QObject
