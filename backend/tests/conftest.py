"""注册 Backend 测试共享 Fixture，具体实现统一放在 ``tests.support``。"""

# 使用 pytest plugin 注册 Fixture，可让 unit、module、contract、integration 各层复用同一套
# 隔离应用，同时避免业务测试从 conftest 这个 pytest 隐式入口导入普通辅助函数。
pytest_plugins = ("tests.support.application",)
