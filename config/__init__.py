"""
配置模块初始化文件
"""

from .settings import Settings
from .chart_types import ChartType
from .intent_types import IntentType


def validate_config() -> list:
    """
    验证配置有效性
    
    Returns:
        错误列表，如果为空则配置有效
    """
    errors = []
    
    # 检查必需的API密钥
    if not Settings.OPENROUTER_API_KEY:
        errors.append("OPENROUTER_API_KEY 未设置")
    
    # 确保日志目录存在
    Settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    return errors


__all__ = ['Settings', 'ChartType', 'IntentType', 'validate_config']
