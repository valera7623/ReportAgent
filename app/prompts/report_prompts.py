"""Prompts for AI table analysis and report recommendations."""

SYSTEM_PROMPT = """
Ты — аналитик данных, специалист по визуализации и извлечению инсайтов из табличных данных.

Анализируй данные и предлагай:
1. Определение колонок (дата, числовые, категориальные, текстовые)
2. Рекомендации по типам графиков (bar, line, pie, scatter, area, heatmap)
3. Краткое описание данных (2-3 предложения)
4. Топ-5 инсайтов (ключевые выводы)
5. Предлагаемые агрегации (sum, mean, median, count, min, max)

Всегда возвращай ответ строго в формате JSON без markdown.
Используй только реальные имена колонок из данных.
"""

FEW_SHOT_EXAMPLES = """
Пример 1:
Данные: sales_data.csv (month, product, sales, profit, region)
Ответ:
{
  "columns": {
    "date": "month",
    "numeric": ["sales", "profit"],
    "category": ["product", "region"],
    "text": []
  },
  "suggested_charts": [
    {"type": "bar", "x": "month", "y": "sales", "title": "Продажи по месяцам"},
    {"type": "pie", "x": "product", "y": "sales", "title": "Доля продуктов в продажах"}
  ],
  "description": "Данные о продажах за 2024 год по месяцам, продуктам и регионам. Всего 4 продукта, 6 регионов.",
  "insights": [
    "Продажи выросли на 15% в декабре",
    "Продукт A — лидер продаж (35% от общего объёма)",
    "Регион Москва генерирует 40% выручки"
  ],
  "aggregations": {
    "sales": ["sum", "mean", "max"],
    "profit": ["sum", "mean"]
  }
}

Пример 2:
Данные: employee_data.csv (id, name, department, salary, tenure, rating)
Ответ:
{
  "columns": {
    "date": null,
    "numeric": ["salary", "tenure", "rating"],
    "category": ["department"],
    "text": ["name"]
  },
  "suggested_charts": [
    {"type": "bar", "x": "department", "y": "salary", "title": "Средняя зарплата по отделам"},
    {"type": "scatter", "x": "tenure", "y": "salary", "title": "Зависимость зарплаты от стажа"}
  ],
  "description": "Данные о 150 сотрудниках: отделы, зарплаты, стаж, оценки эффективности.",
  "insights": [
    "Средняя зарплата в отделе IT на 30% выше, чем в других отделах",
    "Корреляция между стажем и зарплатой положительная",
    "Топ-10% сотрудников имеют оценку выше 90"
  ],
  "aggregations": {
    "salary": ["mean", "min", "max", "median"],
    "tenure": ["mean", "max"]
  }
}
"""

AI_RESPONSE_JSON_SCHEMA_HINT = """
{
  "columns": {
    "date": "column name or null",
    "numeric": ["col1"],
    "category": ["col1"],
    "text": ["col1"]
  },
  "suggested_charts": [
    {"type": "bar|line|pie|scatter|area|heatmap", "x": "col", "y": "col or null", "title": "string"}
  ],
  "description": "string",
  "insights": ["string"],
  "aggregations": {"column": ["sum", "mean", "median", "count", "min", "max"]}
}
"""
