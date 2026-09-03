"""统一日志 Formatter 与真实 SQLAlchemy 日志记录的集成测试。"""

import logging
from io import StringIO

import pytest
from sqlalchemy import create_engine, text

from app.core.logging import ConsoleFormatter, JsonFormatter


@pytest.mark.parametrize("formatter", [ConsoleFormatter(), JsonFormatter()])
def test_sqlalchemy_hides_bound_parameters_in_unified_output(
    formatter: logging.Formatter,
) -> None:
    """真实 SQLAlchemy 记录经过两种 Formatter 时都不能包含绑定参数值。"""

    secret_parameter = "sql-parameter-must-not-leak"
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger("sqlalchemy.engine")
    previous_state = (list(logger.handlers), logger.level, logger.propagate)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    engine = create_engine("sqlite://", echo=False, hide_parameters=True)

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT :private_value"),
                {"private_value": secret_parameter},
            )
    finally:
        engine.dispose()
        logger.handlers = previous_state[0]
        logger.setLevel(previous_state[1])
        logger.propagate = previous_state[2]
        handler.close()

    rendered = stream.getvalue()
    assert secret_parameter not in rendered
    assert "SQL parameters hidden due to hide_parameters=True" in rendered
