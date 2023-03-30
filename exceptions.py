class NoEnvironmentVariables(Exception):
    """Отсутствует одна или несколько переменных окружения."""


class NoDocumentedKeyInDict(KeyError):
    """В ответе отсутствует задокументированный ключ словаря."""


class UndocumentedDataType(TypeError):
    """Получен незадокументированный API тип данных."""
