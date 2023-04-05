import logging
import time
from functools import wraps
from http import HTTPStatus
from operator import itemgetter
from pathlib import Path
from typing import Any

import requests
import telegram

from constants import (
    ENDPOINT,
    FIRST_ELEMENT,
    HEADERS,
    HOMEWORK_VERDICTS,
    PRACTICUM_TOKEN,
    RETRY_PERIOD,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
    TOKEN_NAMES,
)
from exceptions import (
    NoDocumentedKeyInDict,
    NoEnvironmentVariables,
    UndocumentedDataType,
)

log_file = Path(__file__) / 'main.log'

logging.basicConfig(
    level=logging.DEBUG,
    filename=log_file.name,
    format=('%(asctime)s - %(funcName)s - %(levelname)s - %(message)s'),
    encoding='utf-8',
)


def send_message_logging(func):
    """Логирование вызова функции send_message.

    Args:
        func: функция send_message(), отправляющая сообщение в bot.

    Returns:
        wrapper: логирование вызова функции send_message().
    """
    @wraps(func)
    def wrapper(*args: tuple, **kwargs: dict[str, Any]) -> None:
        logging.debug(
            'Вызов функции: %s с аргументами: bot: %s, '
            'текст отправляемого сообщения: %s',
            func.__name__, args[0], args[1],
        )
        try:
            func(*args, **kwargs)
        except telegram.error.TelegramError as er:
            logging.exception(
                'Функции %s не удалось отправить сообщение в Telegram bot. '
                'Ошибка: %s', func.__name__, er,
            )
    return wrapper


def check_tokens() -> None:
    """Проверяет доступность переменных окружения.

    Raises:
        NoEnvironmentVariables: вызывается исключение при отсутствии
            одной или нескольких переменных окружения.
    """
    env_variables = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
    ]
    for var in env_variables:
        if var is None:
            missing_env = [
                token for token in globals()
                if globals()[token] is None and token in TOKEN_NAMES
            ]
            logging.critical(
                'Отсутствует одна или несколько переменных окружения: %s',
                ', '.join(missing_env),
            )
            raise NoEnvironmentVariables(
                f'Переменная окружения {", ".join(missing_env)} отсутствует.',
            )


@send_message_logging
def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram bot.

    Args:
        bot: объект класса telegram.Bot.
        message: строка сообщения для отправки в bot.
    """
    bot.send_message(TELEGRAM_CHAT_ID, message)
    logging.debug('Сообщение успешно отправлено в Telegram bot')


def get_api_answer(timestamp: int) -> dict[str, Any]:
    """Делает запрос к ENDPOINT API-сервиса.

    Args:
        timestamp: временная метка в формате unixtime.

    Returns:
        dict: при успешном запросе к API функция возвращает словарь.

    Raises:
        RequestException: вызывается исключение при неудачном
            запросе к ENDPOINT API.
        HTTPError: вызывается исключение, если при запросе к
            к ENDPOINT API код ответа != 200.
    """
    try:
        response_from_api = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={
                'from_date': timestamp,
            },
        )
    except requests.RequestException:
        raise requests.RequestException(
            f'Ошибка в функции {get_api_answer.__name__} '
            'при запросе ENDPOINT сервер вернул код '
            f'{response_from_api.status_code}',
        )
    if response_from_api.status_code != HTTPStatus.OK:
        raise requests.HTTPError(
            'при запросе сервер вернул код '
            f'{response_from_api.status_code}',
        )
    return response_from_api.json()


def check_response(response: dict) -> None:
    """Проверяет ответ API на соответствие документации.

    Args:
        response: словарь, полученный при запросе к ENDPOINT API.

    Raises:
        UndocumentedDataType: вызывается исключение, если ответ, полученный
            при запросе к ENDPOINT API, не соответствует документации.
    """
    if isinstance(response, dict) and all(
        key in response for key in ('current_date', 'homeworks')
    ) and isinstance(response.get('homeworks'), list):
        logging.debug('Полученные данные соответствуют документации API.')
    else:
        raise UndocumentedDataType(
            'Ключ homeworks отсутствует в аргументе response '
            f'функции {check_response.__name__}.',
        )


def parse_status(homework: dict) -> str:
    """Извлекает из homework информацию о статусе домашней работы.

    Args:
        homework: словарь с последней по времени домашней работой.

    Returns:
        str: возвращает сообщение о статусе домашней работы для
            отправки в telegram bot.

    Raises:
        NoDocumentedKeyInDict: вызывается исключение при отсутствии
            ключей в словаре, которые описаны в документации к API.
    """
    if 'status' not in homework:
        raise NoDocumentedKeyInDict(
            'Ключ status отсутствует в словаре homework '
            f'функции {parse_status.__name__}.',
        )
    if 'homework_name' not in homework:
        raise NoDocumentedKeyInDict(
            'Ключ homework_name отсутствует в словаре homework '
            f'функции {parse_status.__name__}.',
        )
    try:
        homework_name, status = itemgetter('homework_name', 'status')(homework)
    except NoDocumentedKeyInDict:
        raise NoDocumentedKeyInDict(
            'В словаре homework отсутствует один '
            'из задокументированных ключей',
        )
    if status not in HOMEWORK_VERDICTS:
        raise NoDocumentedKeyInDict(
            f'В функции {parse_status.__name__} ключ {status} отсутствует '
            'в словаре HOMEWORK_VERDICTS.',
        )
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response_from_api = get_api_answer(timestamp)
            check_response(response_from_api)
            if response_from_api['homeworks']:
                message = parse_status(
                    response_from_api['homeworks'][FIRST_ELEMENT],
                )
                send_message(bot, message)
            else:
                notification = 'Отсутствует новый статус домашней работы.'
                logging.debug(notification)
            timestamp = response_from_api['current_date']

        except Exception as error:
            message: str = f'Сбой в работе программы: {error}'
            logging.error('Сбой в работе программы: %s', error)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
