import pytest
from main import data, action


def test_action_increments_count_and_uses_total(monkeypatch):
    """Тест проверяет, что action корректно обрабатывает данные при наличии ключа 'total'."""
    # Сброс данных к начальному состоянию
    data["count"] = 0
    data["total"] = 100

    # Мокаем JSONResponse чтобы проверить передаваемые данные
    from fastapi.responses import JSONResponse
    captured = {}

    class MockJSONResponse:
        def __init__(self, content):
            captured['content'] = content
            self.content = content

        def __call__(self):
            return self.content

    monkeypatch.setattr("main.JSONResponse", MockJSONResponse)

    # Вызываем action
    action()

    # Проверяем, что count увеличился и result верный
    assert data["count"] == 1, "Count должен увеличиться на 1"
    assert captured['content']['count'] == 1, "Ответ должен содержать count=1"
    assert captured['content']['result'] == 101, "Результат должен быть total+1 = 101"


def test_action_works_with_different_total(monkeypatch):
    """Тест проверяет, что action корректно работает с произвольным значением total."""
    from main import data

    # Устанавливаем конкретные значения
    data["count"] = 5
    data["total"] = 200

    from fastapi.responses import JSONResponse
    class MockJSONResponse:
        def __init__(self, content):
            self.content = content
            self.response_data = content

    monkeypatch.setattr("main.JSONResponse", MockJSONResponse)

    # Вызываем action
    action()

    # Проверяем результат
    assert data["count"] == 6, "Count должен увеличиться на 1"