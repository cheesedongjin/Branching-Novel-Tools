import os

LANG_FILE = os.path.join(os.path.dirname(__file__), 'language.txt')


def _load_language() -> str:
    try:
        with open(LANG_FILE, encoding='utf-8') as f:
            return f.read().strip() or 'en'
    except OSError:
        return 'en'


LANG = _load_language()

_STRINGS = {
    'en': {
        'warning': 'Warning',
        'error': 'Error',
        'start_over': 'Start Over',
        'reset_warning': 'All progress will be lost.\nRestart from the beginning?',
        'invalid_start': 'Invalid start branch.',
        'exit': 'Exit',
        'missing_target': 'Target branch does not exist: {id}',
        'select_novel': 'Select Novel File',
        'parse_error': 'Parse Error',
        'read_error': 'An error occurred while reading the file:\n{err}',
        'file_not_found': 'File not found: {path}',
        'update_title': 'Update',
        'update_available': '{app} {ver} is available. Update now?',
        'update_started': 'Installer has been launched.',
        'no_content': '(no content)',
    },
    'korean': {
        'warning': '경고',
        'error': '오류',
        'start_over': '처음부터',
        'reset_warning': '지금까지의 진행 상황이 사라집니다.\n처음부터 다시 시작하시겠습니까?',
        'invalid_start': '시작 분기가 유효하지 않습니다.',
        'exit': '나가기',
        'missing_target': '타겟 분기가 존재하지 않습니다: {id}',
        'select_novel': '소설 파일 선택',
        'parse_error': '파싱 오류',
        'read_error': '파일을 읽는 중 오류가 발생했습니다:\n{err}',
        'file_not_found': '파일을 찾을 수 없습니다: {path}',
        'update_title': '업데이트',
        'update_available': '{app} {ver} 버전이 있습니다. 지금 업데이트할까요?',
        'update_started': '설치 프로그램이 실행되었습니다.',
        'no_content': '(내용 없음)',
    },
}


def tr(key: str, **kwargs) -> str:
    table = _STRINGS.get(LANG, _STRINGS['en'])
    text = table.get(key, key)
    return text.format(**kwargs)
