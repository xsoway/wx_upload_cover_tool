#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time     : 2025/10/15 20:10
# @File     : logger.py
"""
🎯 通用日志模块（模块级日志文件版 · 兼容增强版）

功能特性：
- 支持彩色控制台输出
- 支持每日自动分割日志文件（保留最近7天）
- 支持模块级日志文件命名，例如：
    logs/chat_interface_20251015.log
    logs/file_manager_20251015.log
- 自定义日志级别：VERBOSE / NOTICE / SUCCESS
- ✅ 同名日志文件内容自动追加（不会覆盖历史日志）
- ✅ 向后兼容 Python < 3.11 无 mode 参数的版本
"""

import os
import logging
import logging.handlers
import colorlog
from datetime import datetime

# ==============================
# 📦 自定义日志级别
# ==============================
VERBOSE = 15
NOTICE = 25
SUCCESS = 35

logging.addLevelName(VERBOSE, "VERBOSE")
logging.addLevelName(NOTICE, "NOTICE")
logging.addLevelName(SUCCESS, "SUCCESS")


class CustomLogger(logging.Logger):
    """自定义Logger类，支持新日志级别"""

    def verbose(self, msg, *args, **kwargs):
        if self.isEnabledFor(VERBOSE):
            self._log(VERBOSE, msg, args, **kwargs)

    def notice(self, msg, *args, **kwargs):
        if self.isEnabledFor(NOTICE):
            self._log(NOTICE, msg, args, **kwargs)

    def success(self, msg, *args, **kwargs):
        if self.isEnabledFor(SUCCESS):
            self._log(SUCCESS, msg, args, **kwargs)


# ==============================
# 🧩 自定义文件Handler（始终以追加模式打开）
# ==============================
class SafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """兼容旧版本的文件Handler，始终以追加模式打开文件"""
    def _open(self):
        return open(self.baseFilename, "a", encoding=self.encoding)


class GetLogger:
    """日志工厂类，可根据模块名生成独立日志文件"""

    _loggers = {}

    @classmethod
    def get_logger(cls, module_name: str = "main"):
        """
        获取指定模块名的日志实例（单例模式）
        :param module_name: 模块名称（如 chat_interface、file_manager）
        :return: logging.Logger 对象
        """
        if module_name in cls._loggers:
            return cls._loggers[module_name]

        # ========== 创建日志目录（基于项目根，任意工作目录一致） ==========
        tool_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(tool_root, "logs")
        os.makedirs(log_dir, exist_ok=True)

        # ========== 文件名格式 ==========
        date_str = datetime.now().strftime("%Y%m%d")
        log_filename = os.path.join(log_dir, f"{module_name}_{date_str}.log")

        # ========== 配置Logger ==========
        logging.setLoggerClass(CustomLogger)
        logger = logging.getLogger(module_name)
        logger.setLevel(logging.DEBUG)

        # ✅ 避免重复添加Handler（防止日志重复输出）
        if any(isinstance(h, logging.handlers.TimedRotatingFileHandler) for h in logger.handlers):
            return logger

        # 控制台日志（彩色）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        color_formatter = colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s][%(name)s][%(filename)s:%(lineno)d][%(levelname)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "VERBOSE": "blue",
                "INFO": "green",
                "NOTICE": "purple",
                "WARNING": "yellow",
                "SUCCESS": "green,bold",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
            style="%",
        )
        console_handler.setFormatter(color_formatter)

        # ==============================
        # 📁 文件日志（按天分割 + 自动追加）
        # ==============================
        file_handler = SafeTimedRotatingFileHandler(
            filename=log_filename,
            when="midnight",   # 每天午夜分割
            interval=1,
            backupCount=7,     # 保留7天
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "[%(asctime)s][%(name)s][%(filename)s:%(lineno)d][%(levelname)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)

        # 添加到logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        # 缓存并返回
        cls._loggers[module_name] = logger
        logger.notice(f"🟢 模块日志已初始化: {log_filename}")
        return logger


# ✅ 默认全局日志对象（主程序使用）
log = GetLogger.get_logger("logs")


# ==============================
# ✅ 模块自测
# ==============================
if __name__ == "__main__":
    log_main = GetLogger.get_logger("test_logger")
    log_main.debug("调试信息")
    log_main.verbose("详细日志")
    log_main.info("普通信息")
    log_main.notice("通知级日志")
    log_main.warning("警告信息")
    log_main.success("操作成功！")
    log_main.error("错误信息")
    log_main.critical("致命错误")