"""Telegram bot for checking homework status from Yandex Practicum."""

import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv

load_dotenv()

# Настройка логгера с улучшенным форматом
log_format = (
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s - '
    '[%(filename)s:%(lineno)d]'
)
logging.basicConfig(
    level=logging.DEBUG,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), 'homework_bot.log')
        )
    ]
)

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class InvalidResponseCodeError(Exception):
    """Исключение для неверного кода ответа API."""

    pass


class MissingTokenError(Exception):
    """Исключение для отсутствующих токенов."""

    pass


def check_tokens():
    """Проверяет доступность обязательных переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing_tokens = [name for name, value in tokens.items() if not value]
    if missing_tokens:
        error_msg = (
            f'Отсутствуют обязательные переменные окружения: {missing_tokens}'
        )
        logger.critical(error_msg)
        raise MissingTokenError(error_msg)


def send_message(bot, message):
    """Отправка сообщения в чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        logger.error(f'Ошибка отправки сообщения: {error}')
        return False
    logger.debug(f'Сообщение отправлено: {message}')
    return True


def get_api_answer(timestamp):
    """Выполняет запрос к API и возвращает ответ."""
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }

    logger.info(
        f'Запрос к API: {request_params["url"]} '
        f'с параметрами {request_params["params"]}'
    )

    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            f'Ошибка подключения: {error}. '
            f'Параметры запроса: {request_params}'
        )

    if response.status_code != HTTPStatus.OK:
        raise InvalidResponseCodeError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа: {response.status_code}, '
            f'Причина: {response.reason}, '
            f'Текст: {response.text}'
        )

    return response.json()


def check_response(response):
    """Проверяет ответ API."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарём')
    if 'homeworks' not in response:
        raise KeyError('Отсутствует ключ "homeworks"')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Homeworks не является списком')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API')
    if 'status' not in homework:
        raise KeyError('Отсутствует ключ "status" в ответе API')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданный статус работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except MissingTokenError as error:
        logger.critical(error)
        sys.exit('Отсутствуют обязательные переменные окружения')

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_status_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logger.debug('Новых статусов нет')
                continue

            homework = homeworks[0]
            current_status_message = parse_status(homework)

            if current_status_message != last_status_message:
                if send_message(bot, current_status_message):
                    logger.debug('Статус домашней работы отправлен')
                    last_status_message = current_status_message
                    timestamp = response.get('current_date', timestamp)

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.exception(error_message)
            if error_message != last_status_message and send_message(
                bot, error_message
            ):
                last_status_message = error_message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
