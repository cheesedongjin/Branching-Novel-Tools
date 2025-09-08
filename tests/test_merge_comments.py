import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from branching_novel_editor import ChapterEditor


def _merge(editor, original: str, updated: str) -> str:
    return editor._merge_comments(original, updated)


def test_block_comment_not_duplicated_after_multiple_merges():
    editor = ChapterEditor.__new__(ChapterEditor)
    original = ';\nblock\n;\nline1\n'
    updated = 'line1\n'
    first = _merge(editor, original, updated)
    second = _merge(editor, first, updated)
    assert first == second == ';\nblock\n;\nline1'


def test_block_comment_at_end_not_duplicated_when_merging_same():
    editor = ChapterEditor.__new__(ChapterEditor)
    original = 'line1\n;\nblock\n;\n'
    merged = _merge(editor, original, original)
    assert merged == original.rstrip()

