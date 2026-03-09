import logging
import sys
import time
from pythonjsonlogger import jsonlogger
from fastapi import Request

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)

    # File Handle
    file_handler = logging.FileHandler("app.log")
    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(message)s %(url)s %(method)s %(process_time)s"
    )

    file_handler.setFormatter(json_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


logger = logging.getLogger(__name__)

async def logging_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    end = time.time()

    process_time = round(end - start, 4)

    logger.info(
        "Request processed",
        extra={
            "url": request.url.path,
            "method": request.method,
            "process_time": process_time
        }
    )

    return response
