from openchecker.checkers.sonar_checker import _build_sonar_url


def test_sonar_urls_have_one_separator_after_configured_host():
    assert _build_sonar_url({'host': 'https://sonar.example/sonar/'}, '/api/projects/search') == (
        'https://sonar.example/sonar/api/projects/search'
    )
    assert _build_sonar_url({'host': 'http://127.0.0.1:9000/'}, 'api/projects/search') == (
        'http://127.0.0.1:9000/api/projects/search'
    )
