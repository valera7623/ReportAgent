"""Agent 4: build PDF report and send via SMTP."""

from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.preview.summary import build_key_metrics
from app.self_healing.healing_decorator import with_self_healing
from app.utils.fonts import PDF_FONT, PDF_FONT_BOLD, ensure_pdf_fonts
from app.utils.logger import get_logger
from app.utils.metrics import track_agent_metrics

logger = get_logger("agent_sender", "log_sender.log")

PDF_BASE_DIR = Path(os.getenv("PDF_DIR", "/app/storage/pdfs"))
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@reportagent.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

TABLE_CONTENT_WIDTH = 16 * cm


def _pdf_text(value: Any) -> str:
    return escape("" if value is None else str(value))


def _table_cell_style(
    body_style: ParagraphStyle,
    *,
    bold: bool = False,
    header: bool = False,
) -> ParagraphStyle:
    return ParagraphStyle(
        f"TableCell_{'Header' if header else 'Bold' if bold else 'Body'}",
        parent=body_style,
        fontName=PDF_FONT_BOLD if bold or header else PDF_FONT,
        fontSize=8,
        leading=10,
        textColor=colors.whitesmoke if header else body_style.textColor,
        wordWrap="CJK",
    )


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_pdf_text(value), style)


def _paragraph_rows(
    rows: list[list[Any]],
    cell_style: ParagraphStyle,
    *,
    header_style: ParagraphStyle | None = None,
    label_col: bool = False,
) -> list[list[Paragraph]]:
    wrapped: list[list[Paragraph]] = []
    for row_idx, row in enumerate(rows):
        if row_idx == 0 and header_style is not None:
            wrapped.append([_p(cell, header_style) for cell in row])
            continue
        if label_col and len(row) >= 2:
            wrapped.append([_p(row[0], _table_cell_style(cell_style, bold=True)), *[_p(cell, cell_style) for cell in row[1:]]])
            continue
        wrapped.append([_p(cell, cell_style) for cell in row])
    return wrapped


def _table_style(*extra: tuple[Any, ...]) -> TableStyle:
    base: list[tuple[Any, ...]] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    base.extend(extra)
    return TableStyle(base)


def _column_widths(count: int, *, weights: list[float] | None = None) -> list[float]:
    if count <= 0:
        return []
    if weights and len(weights) == count:
        total = sum(weights)
        return [TABLE_CONTENT_WIDTH * (weight / total) for weight in weights]
    return [TABLE_CONTENT_WIDTH / count] * count


def _resolve_email(visualized: dict[str, Any], preferences: dict[str, Any] | None) -> str | None:
    email = visualized.get("email")
    if email:
        return email
    prefs = preferences or visualized.get("preferences") or {}
    return prefs.get("default_email")


def _try_load_logo(logo_url: str | None, task_id: str) -> Path | None:
    if not logo_url:
        return None
    try:
        pdf_dir = PDF_BASE_DIR / task_id
        pdf_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if ".png" in logo_url.lower() else ".jpg"
        logo_path = pdf_dir / f"company_logo{suffix}"
        with urlopen(logo_url, timeout=15) as response:
            logo_path.write_bytes(response.read())
        return logo_path
    except Exception as exc:
        logger.warning("Could not download company logo from %s: %s", logo_url, exc)
        return None


def _cell_text(value: Any, max_len: int = 120) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _append_data_sample(
    story: list[Any],
    visualized: dict[str, Any],
    *,
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
    limit: int = 50,
    max_cols: int = 6,
) -> None:
    columns: list[str] = list(visualized.get("columns") or [])
    data: list[Any] = visualized.get("data") or []
    if not columns or not data:
        return

    shown_cols = columns[:max_cols]
    total_rows = int(visualized.get("row_count") or len(data))
    shown_rows = min(limit, len(data))
    cell_style = _table_cell_style(body_style)
    header_style = _table_cell_style(body_style, header=True)

    story.append(Paragraph("Data Sample", heading_style))
    story.append(
        Paragraph(
            f"Showing {shown_rows} of {total_rows} rows"
            + (f" ({len(columns)} columns, first {len(shown_cols)} shown)" if len(columns) > max_cols else ""),
            body_style,
        )
    )

    table_data: list[list[Any]] = [shown_cols]
    for row in data[:shown_rows]:
        if isinstance(row, dict):
            table_data.append([_cell_text(row.get(col)) for col in shown_cols])
        elif isinstance(row, (list, tuple)):
            table_data.append([_cell_text(cell) for cell in row[: len(shown_cols)]])
        else:
            table_data.append([_cell_text(row)])

    col_count = len(shown_cols)
    data_table = Table(
        _paragraph_rows(table_data, cell_style, header_style=header_style),
        colWidths=_column_widths(col_count),
        repeatRows=1,
    )
    data_table.setStyle(
        _table_style(
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        )
    )
    story.append(data_table)
    story.append(Spacer(1, 0.5 * cm))


def _build_pdf(visualized: dict[str, Any], pdf_path: Path, logo_path: Path | None = None) -> None:
    ensure_pdf_fonts()
    task_id = visualized["task_id"]
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontName=PDF_FONT_BOLD,
        fontSize=18,
        spaceAfter=12,
        textColor=colors.HexColor("#1a1a2e"),
    )
    heading_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName=PDF_FONT_BOLD,
        fontSize=14,
        spaceBefore=14,
        spaceAfter=8,
        textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=PDF_FONT,
    )
    table_cell = _table_cell_style(body_style)
    table_header = _table_cell_style(body_style, header=True)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story: list[Any] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if logo_path and logo_path.exists():
        story.append(Image(str(logo_path), width=4 * cm, height=2 * cm))
        story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("ReportAgent — Data Report", title_style))
    story.append(Paragraph(f"Generated: {now}", body_style))
    story.append(Paragraph(f"Task ID: {task_id}", body_style))
    story.append(Paragraph(f"Source: {visualized.get('source', 'N/A')}", body_style))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Overview", heading_style))
    overview_data = [
        ["Rows", str(visualized.get("row_count", "—"))],
        ["Columns", str(visualized.get("column_count", "—"))],
        ["Recipient", visualized.get("email", "—")],
    ]
    overview_table = Table(
        _paragraph_rows(overview_data, table_cell, label_col=True),
        colWidths=[5 * cm, 11 * cm],
    )
    overview_table.setStyle(
        _table_style(
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        )
    )
    story.append(overview_table)
    story.append(Spacer(1, 0.5 * cm))

    key_metrics = build_key_metrics(visualized)
    if key_metrics:
        story.append(Paragraph("Key Statistics", heading_style))
        metrics_data = [[str(k), str(v)] for k, v in key_metrics.items()]
        metrics_table = Table(
            _paragraph_rows(metrics_data, table_cell, label_col=True),
            colWidths=[7 * cm, 9 * cm],
        )
        metrics_table.setStyle(
            _table_style(
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            )
        )
        story.append(metrics_table)
        story.append(Spacer(1, 0.5 * cm))

    numeric_summary: dict[str, dict[str, float | int]] = visualized.get("numeric_summary") or {}
    if numeric_summary:
        story.append(Paragraph("Numeric Statistics", heading_style))
        table_data = [["Column", "Sum", "Mean", "Min", "Max", "Count"]]
        for col, stats in numeric_summary.items():
            table_data.append(
                [
                    col,
                    str(stats.get("sum", "—")),
                    str(stats.get("mean", "—")),
                    str(stats.get("min", "—")),
                    str(stats.get("max", "—")),
                    str(stats.get("count", "—")),
                ]
            )
        num_table = Table(
            _paragraph_rows(table_data, table_cell, header_style=table_header),
            colWidths=_column_widths(6, weights=[3, 2, 2, 2, 2, 2]),
            repeatRows=1,
        )
        num_table.setStyle(
            _table_style(
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4C72B0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            )
        )
        story.append(num_table)
        story.append(Spacer(1, 0.5 * cm))

    categorical_summary: dict[str, list[dict[str, Any]]] = visualized.get("categorical_summary") or {}
    if categorical_summary:
        story.append(Paragraph("Top Categories", heading_style))
        for col, items in categorical_summary.items():
            story.append(Paragraph(f"<b>{col}</b>", body_style))
            cat_data = [["Value", "Count", "%"]]
            for item in items:
                cat_data.append([item["value"], str(item["count"]), f"{item['percent']}%"])
            cat_table = Table(
                _paragraph_rows(cat_data, table_cell, header_style=table_header),
                colWidths=_column_widths(3, weights=[7, 2, 2]),
            )
            cat_table.setStyle(
                _table_style(
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#55A868")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                )
            )
            story.append(cat_table)
            story.append(Spacer(1, 0.3 * cm))

    _append_data_sample(story, visualized, heading_style=heading_style, body_style=body_style)

    chart_paths: list[str] = visualized.get("chart_paths") or []
    if chart_paths:
        story.append(Paragraph("Charts", heading_style))
        for chart_path in chart_paths:
            path = Path(chart_path)
            if path.exists():
                img = Image(str(path), width=16 * cm, height=9 * cm)
                story.append(img)
                story.append(Spacer(1, 0.3 * cm))

    doc.build(story)


def _send_email(to_email: str, pdf_path: Path, task_id: str) -> None:
    if not SMTP_HOST or SMTP_HOST == "localhost":
        logger.warning("SMTP not configured; skipping email send for task %s", task_id)
        return

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = f"Your ReportAgent PDF Report — {task_id[:8]}"

    body = (
        "Hello,\n\n"
        "Your data report has been generated and is attached as a PDF.\n\n"
        f"Task ID: {task_id}\n\n"
        "— ReportAgent"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=pdf_path.name,
        )
        msg.attach(attachment)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        logger.info("Email sent to %s for task %s", to_email, task_id)
    except Exception as exc:
        raise AgentError(
            f"Failed to send email via SMTP ({SMTP_HOST}:{SMTP_PORT}): {exc}",
            agent="sender",
        ) from exc


@with_self_healing("sender")
@track_agent_metrics("sender")
def run_sender(visualized: dict[str, Any], preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate PDF and send it to the recipient."""
    try:
        prefs = preferences or visualized.get("preferences") or {}
        task_id = visualized["task_id"]
        email = _resolve_email(visualized, prefs)
        visualized = {**visualized, "email": email}

        logger.info("Sender started for task %s", task_id)

        pdf_dir = PDF_BASE_DIR / task_id
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"report_{task_id}.pdf"

        logo_url = visualized.get("company_logo_url") or prefs.get("company_logo_url")
        logo_path = _try_load_logo(logo_url, task_id)

        _build_pdf(visualized, pdf_path, logo_path=logo_path)
        logger.info("PDF saved to %s", pdf_path)

        if email:
            _send_email(email, pdf_path, task_id)
            message = f"Report generated and sent to {email}"
        else:
            logger.info("Email skipped for task %s (download via API)", task_id)
            message = "Report generated. Download via GET /tasks/{task_id}/pdf"

        return {
            "task_id": task_id,
            "email": email,
            "pdf_path": str(pdf_path),
            "chart_count": len(visualized.get("chart_paths") or []),
            "status": "completed",
            "message": message,
        }

    except AgentError:
        raise
    except Exception as exc:
        logger.exception("Unexpected sender error")
        raise AgentError(f"Unexpected error while sending report: {exc}", agent="sender") from exc
