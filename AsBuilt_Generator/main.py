"""
AsBuilt Drawings Generator - Main Entry Point
Launches the PyQt6 application for generating As-Built drawings.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui_design import AsBuiltGeneratorWindow


def main():
    """Main application entry point."""
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("AsBuilt Drawings Generator")
    app.setOrganizationName("Contracting Solutions")
    
    # Set global font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Set RTL direction for entire app
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    
    # Create and show main window
    window = AsBuiltGeneratorWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
