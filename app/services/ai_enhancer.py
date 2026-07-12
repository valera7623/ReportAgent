"""AI-powered column detection, chart suggestions, and data insights."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import pandas as pd

try:
    from openai import APIConnectionError, APITimeoutError, RateLimitError
except ImportError:  # pragma: no cover
    APIConnectionError = APITimeoutError = RateLimitError = ()  # type: ignore[misc, assignment]

from app.prompts.report_prompts import AI_RESPONSE_JSON_SCHEMA_HINT, FEW_SHOT_EXAMPLES, SYSTEM_PROMPT
from app.services import ai_cache
from app.utils.logger import get_logger
from app.voice.openai_client import create_openai_client

logger = get_logger("ai_enhancer", "log_api.log")

DATE_KEYWORDS = ("date", "time", "day", "month", "year", "week", "period", "datetime")
VALID_CHART_TYPES = frozenset({"bar", "line", "pie", "scatter", "area", "heatmap"})
VALID_AGGREGATIONS = frozenset({"sum", "mean", "median", "count", "min", "max"})
MAX_RETRIES = 3
AI_ENHANCER_TIMEOUT_SEC = float(os.getenv("AI_ENHANCER_TIMEOUT_SEC", os.getenv("OPENAI_TIMEOUT_SEC", "12")))


def _ai_unavailable_error(exc: Exception) -> bool:
    """Connection/timeout — fall back to heuristics immediately (no retry storm)."""
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "connection",
            "timeout",
            "timed out",
            "unreachable",
            "connect error",
            "name or service not known",
        )
    )


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


class AIEnhancer:
    """Analyze tabular data and suggest charts, aggregations, and insights."""

    def __init__(self) -> None:
        self.model = os.getenv("AI_ENHANCER_MODEL", "gpt-4o-mini")
        self.enabled = _env_bool("AI_ENHANCER_ENABLED", "true")
        self.max_rows = int(os.getenv("AI_ENHANCER_MAX_ROWS", "10000"))
        self.cache_ttl = int(os.getenv("AI_ENHANCER_CACHE_TTL", "86400"))

    def detect_column_types(self, df: pd.DataFrame) -> dict[str, Any]:
        numeric = df.select_dtypes(include="number").columns.tolist()
        datetime_cols = df.select_dtypes(include=["datetime64", "datetimetz"]).columns.tolist()
        category: list[str] = []
        text: list[str] = []

        for col in df.columns:
            if col in numeric or col in datetime_cols:
                continue
            series = df[col].dropna()
            if series.empty:
                continue
            nunique = series.astype(str).nunique()
            if nunique <= min(50, max(2, len(df) // 5)):
                category.append(col)
            else:
                text.append(col)

        date_col: str | None = None
        if datetime_cols:
            date_col = datetime_cols[0]
        else:
            for col in df.columns:
                lower = col.lower()
                if any(kw in lower for kw in DATE_KEYWORDS):
                    date_col = col
                    if col in category:
                        category.remove(col)
                    if col in text:
                        text.remove(col)
                    break

        return {
            "date": date_col,
            "numeric": numeric,
            "category": category,
            "text": text,
        }

    def suggest_chart_type(self, df: pd.DataFrame, x_column: str, y_column: str | None = None) -> str:
        if x_column not in df.columns:
            return "bar"

        x_series = df[x_column]
        x_unique = x_series.astype(str).nunique()

        if y_column and y_column in df.columns:
            y_numeric = pd.api.types.is_numeric_dtype(df[y_column])
            x_is_date = x_column.lower() in DATE_KEYWORDS or pd.api.types.is_datetime64_any_dtype(x_series)
            if x_is_date and y_numeric:
                return "line"
            if pd.api.types.is_numeric_dtype(x_series) and y_numeric:
                return "scatter"
            if x_unique <= 12 and y_numeric:
                return "pie" if x_unique <= 8 else "bar"
            if y_numeric:
                return "bar"

        if pd.api.types.is_numeric_dtype(x_series):
            return "bar"
        if x_unique <= 8:
            return "pie"
        return "bar"

    def suggest_chart_title(self, df: pd.DataFrame, x_column: str, y_column: str | None = None) -> str:
        chart_type = self.suggest_chart_type(df, x_column, y_column)
        if y_column:
            titles = {
                "line": f"{y_column} по {x_column}",
                "pie": f"Распределение {y_column} по {x_column}",
                "scatter": f"{y_column} vs {x_column}",
                "bar": f"{y_column} по {x_column}",
                "area": f"Динамика {y_column} ({x_column})",
                "heatmap": f"Тепловая карта {y_column} × {x_column}",
            }
            return titles.get(chart_type, f"{y_column} — {x_column}")
        return f"Распределение: {x_column}"

    def generate_data_description(self, df: pd.DataFrame) -> str:
        cols = self.detect_column_types(df)
        parts = [f"Данные содержат {len(df)} строк и {len(df.columns)} колонок"]
        if cols["numeric"]:
            parts.append(f"{len(cols['numeric'])} числовых показателей")
        if cols["category"]:
            parts.append(f"{len(cols['category'])} категориальных полей")
        if cols["date"]:
            parts.append(f"временная ось: {cols['date']}")
        return ". ".join(parts) + "."

    def generate_insights(self, df: pd.DataFrame, columns: list[str] | None = None) -> list[str]:
        insights: list[str] = []
        numeric_cols = columns or self.detect_column_types(df)["numeric"]
        for col in numeric_cols[:3]:
            if col not in df.columns:
                continue
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) < 2:
                continue
            first, last = float(series.iloc[0]), float(series.iloc[-1])
            if first != 0:
                change = ((last - first) / abs(first)) * 100
                direction = "выросли" if change > 0 else "снизились"
                insights.append(f"{col}: значения {direction} на {abs(change):.1f}% (первая → последняя строка)")
            insights.append(f"{col}: min={series.min():.2g}, max={series.max():.2g}, mean={series.mean():.2g}")

        cat_cols = self.detect_column_types(df)["category"]
        for col in cat_cols[:2]:
            top = df[col].astype(str).value_counts().head(1)
            if not top.empty:
                value, count = top.index[0], int(top.iloc[0])
                pct = round(count / len(df) * 100, 1)
                insights.append(f"«{value}» — лидер в колонке {col} ({pct}%)")

        return insights[:5]

    def suggest_aggregations(self, df: pd.DataFrame, column: str) -> list[str]:
        if column not in df.columns or not pd.api.types.is_numeric_dtype(df[column]):
            return ["count"]
        return ["sum", "mean", "median", "min", "max", "count"]

    def analyze_dataframe(self, df: pd.DataFrame, *, file_hash: str | None = None) -> dict[str, Any]:
        """Full analysis with Redis cache and OpenAI fallback."""
        if df.empty:
            return self._get_default_suggestions(df)

        limited = df.head(self.max_rows)
        digest = file_hash or self._generate_hash(limited)
        cache_key = f"ai_suggestions:{digest}"

        cached = ai_cache.get_sync(cache_key)
        if cached:
            cached["file_hash"] = digest
            cached["cached"] = True
            return cached

        if not self.enabled or not os.getenv("OPENAI_API_KEY", "").strip():
            result = self._get_default_suggestions(limited, file_hash=digest)
            ai_cache.set_sync(cache_key, result, self.cache_ttl)
            return result

        try:
            result = self._analyze_with_ai(limited)
            result["file_hash"] = digest
            result["source"] = "openai"
            result = self._normalize_suggestions(result, limited)
            ai_cache.set_sync(cache_key, result, self.cache_ttl)
            return result
        except Exception as exc:
            logger.warning("AI analysis failed, using heuristics: %s", exc)
            result = self._get_default_suggestions(limited, file_hash=digest)
            ai_cache.set_sync(cache_key, result, self.cache_ttl)
            return result

    def _analyze_with_ai(self, df: pd.DataFrame) -> dict[str, Any]:
        client = create_openai_client(timeout=AI_ENHANCER_TIMEOUT_SEC)
        prompt = self._build_prompt(self._prepare_data_preview(df), df.shape)
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=2000,
                )
                content = response.choices[0].message.content or "{}"
                return json.loads(content)
            except Exception as exc:
                last_error = exc
                if _ai_unavailable_error(exc):
                    logger.warning("AI Enhancer unavailable (no retry): %s", exc)
                    raise
                if isinstance(exc, RateLimitError) and attempt < MAX_RETRIES:
                    logger.warning("AI Enhancer rate limited, retry %d/%d", attempt, MAX_RETRIES)
                    time.sleep(1.0 * attempt)
                    continue
                logger.warning("AI Enhancer attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(0.5 * attempt)

        raise last_error or RuntimeError("AI analysis failed")

    def _prepare_data_preview(self, df: pd.DataFrame) -> str:
        try:
            describe = df.describe(include="all", datetime_is_numeric=True).transpose()
        except TypeError:
            describe = df.describe(include="all").transpose()
        return f"""
Количество строк: {len(df)}
Количество колонок: {len(df.columns)}
Колонки: {', '.join(map(str, df.columns.tolist()))}
Типы данных:
{df.dtypes.to_string()}

Пример данных (первые 5 строк):
{df.head().to_string()}

Базовая статистика:
{describe.to_string()}
"""

    def _build_prompt(self, preview: str, shape: tuple[int, int]) -> str:
        return f"""
Проанализируй следующие данные ({shape[0]} строк × {shape[1]} колонок) и верни рекомендации в формате JSON.

{preview}

Примеры рекомендаций:
{FEW_SHOT_EXAMPLES}

Схема ответа:
{AI_RESPONSE_JSON_SCHEMA_HINT}
"""

    def _generate_hash(self, df: pd.DataFrame) -> str:
        hash_str = (
            str(df.columns.tolist())
            + str(df.dtypes.tolist())
            + str(df.head(100).values.tolist())
        )
        return hashlib.md5(hash_str.encode()).hexdigest()

    @staticmethod
    def hash_bytes(content: bytes) -> str:
        return hashlib.md5(content).hexdigest()

    def _get_default_suggestions(
        self,
        df: pd.DataFrame,
        *,
        file_hash: str | None = None,
    ) -> dict[str, Any]:
        columns = self.detect_column_types(df)
        suggested_charts: list[dict[str, Any]] = []

        numeric = columns["numeric"]
        category = columns["category"]
        date_col = columns["date"]

        if date_col and numeric:
            y_col = numeric[0]
            suggested_charts.append(
                {
                    "type": "line",
                    "x": date_col,
                    "y": y_col,
                    "title": self.suggest_chart_title(df, date_col, y_col),
                }
            )
        elif numeric:
            suggested_charts.append(
                {
                    "type": "bar",
                    "x": numeric[0],
                    "y": None,
                    "title": self.suggest_chart_title(df, numeric[0]),
                }
            )

        if category and numeric and len(suggested_charts) < 3:
            x_col, y_col = category[0], numeric[0]
            chart_type = self.suggest_chart_type(df, x_col, y_col)
            suggested_charts.append(
                {
                    "type": chart_type,
                    "x": x_col,
                    "y": y_col,
                    "title": self.suggest_chart_title(df, x_col, y_col),
                }
            )

        aggregations = {
            col: self.suggest_aggregations(df, col) for col in numeric[:5]
        }

        return {
            "columns": columns,
            "suggested_charts": suggested_charts[:5],
            "description": self.generate_data_description(df),
            "insights": self.generate_insights(df),
            "aggregations": aggregations,
            "file_hash": file_hash,
            "source": "heuristic",
            "cached": False,
        }

    def _normalize_suggestions(self, raw: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
        columns_raw = raw.get("columns") or {}
        valid_cols = set(map(str, df.columns.tolist()))

        def _filter_cols(items: Any) -> list[str]:
            if not isinstance(items, list):
                return []
            return [c for c in items if c in valid_cols]

        date_col = columns_raw.get("date")
        if date_col not in valid_cols:
            date_col = self.detect_column_types(df)["date"]

        columns = {
            "date": date_col if date_col in valid_cols else None,
            "numeric": _filter_cols(columns_raw.get("numeric")) or self.detect_column_types(df)["numeric"],
            "category": _filter_cols(columns_raw.get("category")) or self.detect_column_types(df)["category"],
            "text": _filter_cols(columns_raw.get("text")),
        }

        charts: list[dict[str, Any]] = []
        for item in raw.get("suggested_charts") or []:
            if not isinstance(item, dict):
                continue
            x_col = item.get("x")
            if x_col not in valid_cols:
                continue
            chart_type = str(item.get("type", "bar")).lower()
            if chart_type not in VALID_CHART_TYPES:
                chart_type = self.suggest_chart_type(df, x_col, item.get("y"))
            y_col = item.get("y")
            if y_col is not None and y_col not in valid_cols:
                y_col = columns["numeric"][0] if columns["numeric"] else None
            charts.append(
                {
                    "type": chart_type,
                    "x": x_col,
                    "y": y_col,
                    "title": item.get("title") or self.suggest_chart_title(df, x_col, y_col),
                }
            )

        if not charts:
            charts = self._get_default_suggestions(df)["suggested_charts"]

        aggregations: dict[str, list[str]] = {}
        raw_aggs = raw.get("aggregations") or {}
        if isinstance(raw_aggs, dict):
            for col, aggs in raw_aggs.items():
                if col not in valid_cols:
                    continue
                if isinstance(aggs, list):
                    filtered = [a for a in aggs if str(a).lower() in VALID_AGGREGATIONS]
                    if filtered:
                        aggregations[col] = filtered

        if not aggregations:
            aggregations = self._get_default_suggestions(df)["aggregations"]

        insights = raw.get("insights") or []
        if not isinstance(insights, list):
            insights = []
        insights = [str(i) for i in insights if i][:5]
        if not insights:
            insights = self.generate_insights(df)

        description = str(raw.get("description") or "").strip() or self.generate_data_description(df)

        return {
            "columns": columns,
            "suggested_charts": charts[:5],
            "description": description,
            "insights": insights,
            "aggregations": aggregations,
            "source": raw.get("source", "openai"),
        }


_default_enhancer: AIEnhancer | None = None


def get_ai_enhancer() -> AIEnhancer:
    global _default_enhancer
    if _default_enhancer is None:
        _default_enhancer = AIEnhancer()
    return _default_enhancer
