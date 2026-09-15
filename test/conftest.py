import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run tests that need API keys or downloaded models",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--integration"):
        return
    skip = pytest.mark.skip(reason="needs --integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
