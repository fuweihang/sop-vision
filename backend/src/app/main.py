"""Uvicorn 生产入口；应用工厂独立放置，供测试和 OpenAPI 导出安全复用。"""

from app.factory import create_app

app = create_app()
