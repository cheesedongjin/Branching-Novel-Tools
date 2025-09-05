"""
Branching Novel GUI (Interactive Fiction with Simple Text Syntax)

Requirements
------------
1. Story content is defined in plain text files with branches.
2. The simple syntax is parsed to play the novel.
3. Run ``python branching_novel.py path/to/story.bnov`` to start.
   (If omitted, a file selection dialog will appear.)
4. Readers can move forward/backward like a book, keeping a history.
5. A chapter list is displayed.

File Syntax
-----------
Metadata (optional):
  ``@title``  - story title
  ``@start``  - starting chapter ID

Chapters:
  ``# chapter_id: Chapter Title``
  Paragraph lines separated by blank lines.
  Choices use ``* button text -> next_chapter_id``.

Example::

  @title: Bambi
  @start: intro

  # intro: Name at the Window
  Bambi opened the window and sighed.
  In the darkness someone called her name.

  * Check outside -> alley
  * Do not answer -> silence
  * Lock the door -> lock

  # alley: The Man in the Alley
  She cautiously pushed the window open.
  Cool night air flowed in. A stranger stood below.

  * Call out to him -> call
  * Close the window -> lock

Design Overview
---------------
1. Parser ``StoryParser`` handles ``@title``/``@start`` and parses chapters
   and choices.
2. Data model consists of ``Story``, ``Chapter``, and ``Choice`` classes.
3. GUI shows chapter list, navigation, text, and choice buttons.
   Reader history is stored so backtracking is possible.
4. Double-clicking a chapter jumps to it and truncates future history.

Notes
-----
- No ASCII art or emoticons.
- Only the Python standard library (Tkinter) is used.
"""

import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from i18n import tr, set_language, set_language_from_file, get_user_lang_file

from auto_update import check_for_update
from story_parser import Story, ParseError, StoryParser
from branching_novel_app import BranchingNovelApp


APP_NAME = "Branching Novel GUI"
INSTALLER_NAME = "BranchingNovelGUI-Online-Setup.exe"
APP_ID = "0FD4DF37-F7B3-40B1-8715-9667977A8D51"


def load_text_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="Branching Novel GUI")
    parser.add_argument("file", nargs="?", help="Story file path (.bnov)")
    parser.add_argument("--lang", help="language code (e.g., en, ko)")
    args = parser.parse_args()

    if args.lang:
        set_language(args.lang)
    else:
        lang_file = get_user_lang_file("game_language.txt")
        set_language_from_file(lang_file)

    file_path = args.file
    if not file_path:
        # file selection dialog
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title=tr("select_novel"),
            filetypes=[("Branching Novel Files", "*.bnov"), ("All Files", "*.*")]
        )
        root.destroy()
        if not file_path:
            return

    if not os.path.isfile(file_path):
        print(tr("file_not_found", path=file_path))
        sys.exit(1)

    try:
        text = load_text_from_file(file_path)
        parser = StoryParser()
        story = parser.parse(text)
    except ParseError as e:
        messagebox.showerror(tr("parse_error"), str(e))
        sys.exit(1)
    except Exception as e:
        messagebox.showerror(tr("error"), tr("read_error", err=e))
        sys.exit(1)

    app = BranchingNovelApp(story, file_path, show_disabled=story.show_disabled)
    check_for_update(
        app_name=APP_NAME,
        installer_name=INSTALLER_NAME,
        app_id=APP_ID,
    )
    app.mainloop()


if __name__ == "__main__":
    main()

