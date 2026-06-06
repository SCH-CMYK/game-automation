"""
GameAuto 结构化日志 — rotating file handler + console handler

用法:
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("消息")
    logger.error("错误", exc_info=True)
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

PROJECT_DIR = Path(__file__).parent.resolve()
LOGS_DIR = PROJECT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

_loggers: dict[str, logging.Logger] = {}


_configured = False


def _setup_root_logger():
    """配置根 logger，所有子 logger 自动继承"""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger("gameauto")
    root.setLevel(logging.DEBUG)

    # Console handler (INFO 级别)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "[%(name)s:%(levelname)s] %(message)s"
    ))
    root.addHandler(console)

    # File handler (DEBUG 级别, 10MB 轮转, 保留5个)
    today = datetime.now().strftime("%Y%m%d")
    file_handler = RotatingFileHandler(
        LOGS_DIR / f"gameauto_{today}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(name)s:%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)


def get_logger(name: str = "gameauto") -> logging.Logger:
    """获取 logger（自动配置根 logger）"""
    _setup_root_logger()
    return logging.getLogger(name)


def install_crash_handler():
    """注册全局异常处理器，崩溃时记录 traceback 到日志"""
    logger = get_logger("crash")

    def handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "未捕获的异常",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        # 仍然调用默认 handler 打印到 stderr
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handler
    return logger
