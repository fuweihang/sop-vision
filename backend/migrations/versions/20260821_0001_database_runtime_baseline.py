"""建立数据库迁移基线。

修订 ID：0001_database_runtime
前置修订：
创建日期：2026-08-21
"""

from collections.abc import Sequence

revision: str = "0001_database_runtime"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 本 revision 只证明迁移链可运行；Camera 等业务 DDL 由后续步骤添加。
    pass


def downgrade() -> None:
    # 基线不创建业务对象，因此回滚也不执行 DDL。
    pass
