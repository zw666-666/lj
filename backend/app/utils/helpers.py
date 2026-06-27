"""通用工具函数"""
import re


def extract_phone(text: str) -> str:
    """从文本中提取手机号"""
    match = re.search(r"1[3-9]\d{9}", text)
    return match.group() if match else ""


def is_email(text: str) -> bool:
    """判断是否为邮箱地址"""
    return bool(re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", text))
