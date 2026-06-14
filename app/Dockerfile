# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    libfreetype6 \
    fontconfig \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY . /app/app/

RUN mkdir -p /app/storage/pdfs /app/storage/uploads /app/storage/formatted /app/logs /app/app/templates \
    && python - <<'PY'
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt

out = Path("/app/app/templates/template.pptx")
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "ReportAgent Report"
if len(slide.placeholders) > 1:
    slide.placeholders[1].text = "%DATE%\nReportAgent"
content = prs.slides.add_slide(prs.slide_layouts[1])
if content.shapes.title:
    content.shapes.title.text = "Summary"
if len(content.placeholders) > 1:
    content.placeholders[1].text = "%METRICS%"
blank = prs.slides.add_slide(prs.slide_layouts[6])
box = blank.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1))
box.text_frame.text = "%CHART_1%"
prs.save(out)
print("Created", out)
PY

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
