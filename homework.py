import logging
import sys
import time
from http import HTTPStatus

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
)
from exceptions import (
    NoDocumentedKeyInDict,
    NoEnvironmentVariables,
    UndocumentedDataType,
)

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    format=('%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
    encoding='utf-8',
)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    env_variables = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
    ]
    for var in env_variables:
        if var is None:
            logging.critical(
                'Отсутствует одна или несколько переменных окружения.'
            )
            raise NoEnvironmentVariables(
                f'Переменная окружения отсутствует{var}'
            )
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram bot."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Сообщение успешно отправлено в Telegram bot')
    except telegram.error.TelegramError as er:
        logging.error(
            f'Функции {send_message.__name__} не удалось отправить '
            f'сообщение в Telegram bot: {er}'
        )


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    try:
        response_from_api = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={
                'from_date': timestamp,
            },
        )
        if response_from_api.status_code != HTTPStatus.OK:
            raise requests.HTTPError(
                'при запросе сервер вернул код '
                f'{response_from_api.status_code}'
            )
    except requests.RequestException:
        raise requests.RequestException(
            f'Ошибка в функции {get_api_answer.__name__} '
            'при запросе ENDPOINT сервер вернул код '
            f'{response_from_api.status_code}'
        )
    return response_from_api.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if type(response) != dict:
        raise UndocumentedDataType(
            f'Функция {check_response.__name__} ожидает словарь, '
            f'а получила {type(response)}'
        )
    if 'homeworks' not in response:
        raise NoDocumentedKeyInDict(
            'Ключ homeworks отсутствует в арггументе response '
            f'функции {check_response.__name__}.'
        )
    if 'current_date' not in response:
        raise NoDocumentedKeyInDict(
            'Ключ current_date отсутствует в арггументе response '
            f'функции {check_response.__name__}'
        )
    if type(response.get('homeworks')) != list:
        raise UndocumentedDataType(
            f'Функция {check_response.__name__} ожидает в ответе '
            'под ключем homeworks список, а получила словарь.'
        )


def parse_status(homework):
    """Извлекает из информацию о статусе домашней работы."""
    if 'status' not in homework:
        raise NoDocumentedKeyInDict(
            'Ключ status отсутствует в словаре homework '
            f'функции {parse_status.__name__}.'
        )
    if 'homework_name' not in homework:
        raise NoDocumentedKeyInDict(
            'Ключ homework_name отсутствует в словаре homework '
            f'функции {parse_status.__name__}.'
        )
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise NoDocumentedKeyInDict(
            f'В функции {parse_status.__name__} ключ {status} отсутствует '
            'в словаре HOMEWORK_VERDICTS.'
        )
    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except NoEnvironmentVariables:
        sys.exit()

    bot: telegram.Bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp: int = int(time.time())

    while True:
        try:
            response_from_api: dict = get_api_answer(timestamp)
            check_response(response_from_api)
            if response_from_api['homeworks']:
                message: str = parse_status(
                    response_from_api['homeworks'][FIRST_ELEMENT],
                )
                send_message(bot, message)
            else:
                notification: str = 'Отсутствует новый статус домашней работы.'
                logging.debug(notification)
            timestamp: int = response_from_api['current_date']

        except Exception as error:
            message: str = f'Сбой в работе программы: {error}'
            logging.error(f'Сбой в работе программы: {error}')
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
