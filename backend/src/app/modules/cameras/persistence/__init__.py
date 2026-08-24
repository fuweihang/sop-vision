"""Camera 数据库存取代码所在的包。

这里故意不从包根目录重新导出 Repository、ORM 模型或巡检函数。调用方应从具体子模块
导入所需对象，例如从 ``persistence.models`` 导入 ORM 模型。这样 Alembic 只为读取表定义
而导入模型时，不会顺带加载 Repository、Unit of Work 和 FastAPI 依赖。
"""
