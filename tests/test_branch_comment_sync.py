import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from story_parser import StoryParser


def test_branch_comments_sync_from_code():
    text = (
        "@chapter c1: Chapter\n"
        "# b1: Title ;note\n"
        "line1\n"
        "; comment\n"
        "line2\n"
        "* choice -> b2\n"
    )
    parser = StoryParser()
    story = parser.parse(text)
    # Comments are stripped during parse
    br = story.branches['b1']
    assert br.title == 'Title'
    assert br.raw_text == ''

    branch_texts = parser.extract_branch_texts(text)
    for bid, br in story.branches.items():
        if bid in branch_texts:
            br.title, br.raw_text = branch_texts[bid]

    br = story.branches['b1']
    assert br.title == 'Title ;note'
    assert br.raw_text == 'line1\n; comment\nline2'
