"""Cyrillic-capable fonts for PDF reports and matplotlib charts."""

from __future__ import annotations

from pathlib import Path

_pdf_fonts_registered = False

PDF_FONT = "DejaVuSans"
PDF_FONT_BOLD = "DejaVuSans-Bold"


def _dejavu_font_paths() -> tuple[Path, Path]:
    from matplotlib import get_data_path

    base = Path(get_data_path()) / "fonts" / "ttf"
    return base / "DejaVuSans.ttf", base / "DejaVuSans-Bold.ttf"


def ensure_pdf_fonts() -> None:
    """Register DejaVu fonts with ReportLab (idempotent)."""
    global _pdf_fonts_registered
    if _pdf_fonts_registered:
        return

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular_path, bold_path = _dejavu_font_paths()
    if not regular_path.is_file() or not bold_path.is_file():
        raise FileNotFoundError(
            f"DejaVu fonts not found under {regular_path.parent}. "
            "Ensure matplotlib is installed."
        )

    pdfmetrics.registerFont(TTFont(PDF_FONT, str(regular_path)))
    pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD, str(bold_path)))
    _pdf_fonts_registered = True


def configure_matplotlib_fonts() -> None:
    """Use a Unicode font in matplotlib so chart labels render Cyrillic."""
    import matplotlib.pyplot as plt

    regular_path, _ = _dejavu_font_paths()
    if regular_path.is_file():
        plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False
