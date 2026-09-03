"""Cameras 跨层安全测试共享的固定值，不供其他业务模块使用。"""

# 敏感数据门禁要求同一 canary 穿过领域、Schema、ORM、Problem 与日志边界。统一值可以防止某层
# 只屏蔽了自己的测试密码，却遗漏真实请求在另一层的传播路径。
CAMERA_LEAK_SENTINEL = "cameras-mvp-leak-sentinel"
CAMERA_LEAK_RTSP_URL = f"rtsp://admin:{CAMERA_LEAK_SENTINEL}@192.0.2.1:554/Streaming/Channels/101"
