"""remove redundant detector metadata

Revision ID: 20260821_0002
Revises: 20260821_0001
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260821_0002"
down_revision: str | None = "20260821_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE worker_task_parameters
        SET config = config
            - 'camera_id'
            - 'source_id'
            - 'algorithm_id'
            - 'algorithm_version'
        WHERE worker_type = 'detector'
          AND config ?| ARRAY[
              'camera_id',
              'source_id',
              'algorithm_id',
              'algorithm_version'
          ]
        """
    )


def downgrade() -> None:
    # 原始标识不可恢复；使用 task_id 和旧版默认算法信息生成兼容占位值。
    op.execute(
        """
        UPDATE worker_task_parameters
        SET config = config || jsonb_build_object(
            'camera_id', task_id,
            'source_id', task_id,
            'algorithm_id', 'yolo_object_detection',
            'algorithm_version', '0.1.0'
        )
        WHERE worker_type = 'detector'
        """
    )
