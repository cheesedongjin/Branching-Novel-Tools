"""
Branching Novel Editor (GUI)

This editor supports the syntax where multiple branches are placed within a
single chapter. Branches behave like in the game, while chapters group them
like chapters in a book.

Syntax format::

  @title: Story Title
  @start: StartBranchID

  @chapter chapter_id: Chapter Title
  # branch_id: Branch Title
  Paragraph line 1

  Paragraph line 2

  * Button text -> target_branch_id
  * Button text 2 -> target_branch_id2

Notes:
  - Chapter IDs and branch IDs must be unique.
  - Choice targets may point to non-existing branches but validation will warn.
  - Paragraphs are separated by blank lines.

Usage:
  python branching_novel_editor.py
"""

import os
import sys
import re
import ast
import argparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from i18n import tr, set_language, set_language_from_file
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional, Callable, Iterable, Tuple, Union

from auto_update import check_for_update


APP_NAME = "Branching Novel Editor"
INSTALLER_NAME = "BranchingNovelEditor-Online-Setup.exe"

VAR_PATTERN = re.compile(r"\$\{[^}]+\}")


class VarAutocomplete:
    """단순 변수명 자동완성 팝업"""
    def __init__(self, widget: tk.Widget, get_vars: Callable[[], Iterable[str]]):
        self.widget = widget
        self.get_vars = get_vars
        self.popup: Optional[tk.Toplevel] = None
        self.listbox: Optional[tk.Listbox] = None

        # 현재 입력 중인 단어 추적
        self._current_word_start = None
        self._current_filter = ""
        self._all_vars = []
        self._is_filtering = False

        # 이벤트 바인딩
        widget.bind("<KeyPress>", self._on_key_press, add="+")
        widget.bind("<KeyRelease>", self._on_key_release, add="+")
        widget.bind("<Button-1>", self._on_click, add="+")
        widget.bind("<Destroy>", lambda e: self.close(), add="+")

    def _on_key_press(self, event):
        """키 누름 이벤트 처리"""
        if self.popup and self.popup.winfo_exists():
            # ESC로 드롭다운 닫기
            if event.keysym == "Escape":
                self.close()
                return "break"

            # 방향키 처리
            if event.keysym in ("Up", "Down"):
                self._handle_arrow_keys(event)
                return "break"

            # Enter, Tab으로 선택
            if event.keysym in ("Return", "Tab"):
                self._insert()
                return "break"

            # Backspace로 필터링 업데이트
            if event.keysym == "BackSpace":
                self.widget.after(0, self._update_filter)
                return

        # 특수 키들은 드롭다운을 닫지 않음
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                           "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Super_L", "Super_R"):
            return

    def _on_key_release(self, event):
        """키 놓음 이벤트 처리"""
        # 특수 키들은 무시
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                           "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Super_L", "Super_R",
                           "Up", "Down", "Left", "Right", "Return", "Tab", "Escape"):
            return

        self.widget.after(0, self._update_filter)

    def _on_click(self, event):
        """마우스 클릭 처리"""
        if self.popup and self.popup.winfo_exists():
            # 드롭다운 외부 클릭 시 닫기
            try:
                click_x = event.x_root
                click_y = event.y_root
                popup_x = self.popup.winfo_rootx()
                popup_y = self.popup.winfo_rooty()
                popup_w = self.popup.winfo_width()
                popup_h = self.popup.winfo_height()

                if not (popup_x <= click_x <= popup_x + popup_w and
                        popup_y <= click_y <= popup_y + popup_h):
                    self.close()
            except:
                self.close()

        # 클릭 후 새로운 위치에서 자동완성 확인
        self.widget.after(10, self._update_filter)

    def _update_filter(self):
        """현재 커서 위치에서 입력 중인 단어를 확인하고 필터링"""
        try:
            word_info = self._get_current_word()
            if word_info is None:
                self.close()
                return

            word_start, current_word = word_info
            self._current_word_start = word_start
            self._current_filter = current_word

            # 변수 목록 가져오기
            self._all_vars = list(self.get_vars())
            if not self._all_vars:
                self.close()
                return

            # 필터링
            filtered_vars = [var for var in self._all_vars if var.startswith(current_word)]

            # 필터링 결과가 없거나 완전히 일치하는 경우 드롭다운 닫기
            if not filtered_vars or (len(filtered_vars) == 1 and filtered_vars[0] == current_word):
                self.close()
                return

            # 드롭다운 열기 또는 업데이트
            if self.popup and self.popup.winfo_exists():
                self._update_dropdown(filtered_vars)
            else:
                self._open_dropdown(filtered_vars)

        except Exception:
            self.close()

    def _get_current_word(self) -> Optional[tuple[int, str]]:
        """현재 커서 위치에서 입력 중인 단어 정보 반환"""
        if isinstance(self.widget, tk.Text):
            return self._get_current_word_text()
        else:
            return self._get_current_word_entry()

    def _get_current_word_text(self) -> Optional[tuple[str, str]]:
        """Text 위젯에서 현재 단어 정보 반환"""
        try:
            insert = self.widget.index(tk.INSERT)
            line_start = f"{insert.split('.')[0]}.0"
            line_content = self.widget.get(line_start, insert)

            # 단어 경계 찾기 (알파벳, 숫자, 언더스코어만 변수명으로 취급)
            word_pattern = re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*$')
            match = word_pattern.search(line_content)

            if match:
                word_start_col = match.start()
                word = match.group()
                word_start_index = f"{insert.split('.')[0]}.{word_start_col}"
                return (word_start_index, word)

            return None
        except Exception:
            return None

    def _get_current_word_entry(self) -> Optional[tuple[int, str]]:
        """Entry 위젯에서 현재 단어 정보 반환"""
        try:
            cursor_pos = int(self.widget.index(tk.INSERT))
            text = self.widget.get()

            # 커서 위치 이전 텍스트에서 단어 찾기
            before_cursor = text[:cursor_pos]
            word_pattern = re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*$')
            match = word_pattern.search(before_cursor)

            if match:
                word_start = match.start()
                word = match.group()
                return (word_start, word)

            return None
        except Exception:
            return None

    def _open_dropdown(self, filtered_vars: list):
        """드롭다운 열기"""
        self.close()  # 기존 팝업 정리

        # 새 팝업 생성
        self.popup = tk.Toplevel(self.widget.winfo_toplevel())
        self.popup.overrideredirect(True)
        self.popup.transient(self.widget.winfo_toplevel())

        try:
            self.popup.attributes("-topmost", True)
        except Exception:
            pass

        self.popup.withdraw()

        # 리스트박스 생성
        lb = tk.Listbox(self.popup, exportselection=False, height=min(len(filtered_vars), 8))
        lb.pack(fill="both", expand=True)

        for var in filtered_vars:
            lb.insert(tk.END, var)

        if filtered_vars:
            lb.activate(0)
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)

        # 이벤트 바인딩
        lb.bind("<Return>", self._insert, add="+")
        lb.bind("<Tab>", self._insert, add="+")
        lb.bind("<Double-Button-1>", self._insert, add="+")
        lb.bind("<ButtonRelease-1>", self._insert, add="+")
        lb.bind("<Escape>", lambda e: (self.close() or "break"), add="+")

        # 호버 시 활성 항목 갱신
        def _on_motion(e):
            i = lb.nearest(e.y)
            if 0 <= i < lb.size():
                lb.activate(i)
                lb.selection_clear(0, tk.END)
                lb.selection_set(i)
        lb.bind("<Motion>", _on_motion, add="+")

        self.listbox = lb

        # 위치 설정 및 표시
        self.popup.update_idletasks()
        x, y = self._get_popup_position()
        self.popup.geometry(f"+{x}+{y}")
        self.popup.deiconify()

    def _update_dropdown(self, filtered_vars: list):
        """드롭다운 항목 업데이트"""
        if not self.listbox:
            return

        # 리스트박스 업데이트
        self.listbox.delete(0, tk.END)
        for var in filtered_vars:
            self.listbox.insert(tk.END, var)

        # 첫 번째 항목 선택
        if filtered_vars:
            self.listbox.activate(0)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)

            # 높이 조정
            self.listbox.configure(height=min(len(filtered_vars), 8))
            self.popup.update_idletasks()
        else:
            self.close()

    def _get_popup_position(self) -> tuple[int, int]:
        """팝업 위치 계산"""
        try:
            if isinstance(self.widget, tk.Text):
                # Text 위젯의 커서 위치
                bbox = self.widget.bbox(tk.INSERT)
                if bbox:
                    return (self.widget.winfo_rootx() + bbox[0],
                            self.widget.winfo_rooty() + bbox[1] + bbox[3] + 2)
            else:
                # Entry 위젯의 커서 위치
                cursor_pos = int(self.widget.index(tk.INSERT))
                bbox = self.widget.bbox(max(0, cursor_pos - 1))
                if bbox:
                    return (self.widget.winfo_rootx() + bbox[0],
                            self.widget.winfo_rooty() + self.widget.winfo_height() + 2)
        except Exception:
            pass

        # 폴백: 위젯 하단
        return (self.widget.winfo_rootx(),
                self.widget.winfo_rooty() + self.widget.winfo_height() + 2)

    def _handle_arrow_keys(self, event):
        """방향키로 드롭다운 항목 선택"""
        if not self.listbox:
            return

        current = self.listbox.curselection()
        current_index = current[0] if current else 0

        if event.keysym == "Down":
            new_index = min(current_index + 1, self.listbox.size() - 1)
        else:  # Up
            new_index = max(current_index - 1, 0)

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)
        self.listbox.see(new_index)

    def _insert(self, event=None):
        """선택된 변수 삽입"""
        if not self.listbox:
            return "break"

        selection = self.listbox.curselection()
        if not selection:
            return "break"

        var_name = self.listbox.get(selection[0])
        if not var_name:
            return "break"

        # 현재 입력 중인 부분 단어를 선택된 변수로 교체
        if isinstance(self.widget, tk.Text):
            self._insert_text_widget(var_name)
        else:
            self._insert_entry_widget(var_name)

        self.close()
        return "break"

    def _insert_text_widget(self, var_name: str):
        """Text 위젯에 변수 삽입"""
        try:
            if self._current_word_start is None:
                # 현재 위치에 삽입
                insert_pos = self.widget.index(tk.INSERT)
                self.widget.insert(insert_pos, var_name)
                self.widget.mark_set(tk.INSERT, f"{insert_pos}+{len(var_name)}c")
            else:
                # 현재 단어를 변수로 교체
                current_pos = self.widget.index(tk.INSERT)
                self.widget.delete(self._current_word_start, current_pos)
                self.widget.insert(self._current_word_start, var_name)
                self.widget.mark_set(tk.INSERT, f"{self._current_word_start}+{len(var_name)}c")

            self.widget.focus_set()
        except Exception:
            pass

    def _insert_entry_widget(self, var_name: str):
        """Entry 위젯에 변수 삽입"""
        try:
            if self._current_word_start is None:
                # 현재 위치에 삽입
                cursor_pos = int(self.widget.index(tk.INSERT))
                self.widget.insert(cursor_pos, var_name)
                self.widget.icursor(cursor_pos + len(var_name))
            else:
                # 현재 단어를 변수로 교체
                current_pos = int(self.widget.index(tk.INSERT))
                self.widget.delete(self._current_word_start, current_pos)
                self.widget.insert(self._current_word_start, var_name)
                self.widget.icursor(self._current_word_start + len(var_name))

            self.widget.focus_set()
        except Exception:
            pass

    def trigger(self):
        """프로그램적으로 드롭다운 트리거"""
        self.widget.focus_set()
        self._update_filter()

    def _is_word_char(self, char: str) -> bool:
        """변수명에 사용 가능한 문자인지 확인"""
        return char.isalnum() or char == '_'

    def _get_current_word_info_text(self) -> Optional[tuple[str, str]]:
        """Text 위젯에서 현재 단어 정보 반환"""
        try:
            insert = self.widget.index(tk.INSERT)
            insert_line, insert_col = map(int, insert.split('.'))

            # 현재 라인 전체 가져오기
            line_start = f"{insert_line}.0"
            line_end = f"{insert_line}.end"
            line_content = self.widget.get(line_start, line_end)

            if insert_col > len(line_content):
                insert_col = len(line_content)

            # 단어의 시작 찾기
            word_start_col = insert_col
            while word_start_col > 0 and self._is_word_char(line_content[word_start_col - 1]):
                word_start_col -= 1

            # 현재 단어 추출
            current_word = line_content[word_start_col:insert_col]

            # 최소 1글자 이상이고 알파벳이나 언더스코어로 시작해야 함
            if len(current_word) > 0 and (current_word[0].isalpha() or current_word[0] == '_'):
                word_start_index = f"{insert_line}.{word_start_col}"
                return (word_start_index, current_word)

            return None
        except Exception:
            return None

    def _get_current_word_info_entry(self) -> Optional[tuple[int, str]]:
        """Entry 위젯에서 현재 단어 정보 반환"""
        try:
            cursor_pos = int(self.widget.index(tk.INSERT))
            text = self.widget.get()

            # 단어의 시작 찾기
            word_start = cursor_pos
            while word_start > 0 and self._is_word_char(text[word_start - 1]):
                word_start -= 1

            # 현재 단어 추출
            current_word = text[word_start:cursor_pos]

            # 최소 1글자 이상이고 알파벳이나 언더스코어로 시작해야 함
            if len(current_word) > 0 and (current_word[0].isalpha() or current_word[0] == '_'):
                return (word_start, current_word)

            return None
        except Exception:
            return None

    def _get_current_word(self):
        """현재 입력 중인 단어 정보 반환 (위젯 타입에 따라 분기)"""
        if isinstance(self.widget, tk.Text):
            return self._get_current_word_info_text()
        else:
            return self._get_current_word_info_entry()

    def _open_dropdown(self, filtered_vars: list):
        """새 드롭다운 열기"""
        # 새 팝업 생성
        self.popup = tk.Toplevel(self.widget.winfo_toplevel())
        self.popup.overrideredirect(True)
        self.popup.transient(self.widget.winfo_toplevel())

        try:
            self.popup.attributes("-topmost", True)
        except Exception:
            pass

        self.popup.withdraw()

        # 리스트박스 생성
        lb = tk.Listbox(self.popup, exportselection=False, height=min(len(filtered_vars), 8))
        lb.pack(fill="both", expand=True)

        for var in filtered_vars:
            lb.insert(tk.END, var)

        if filtered_vars:
            lb.activate(0)
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)

        # 이벤트 바인딩
        lb.bind("<Return>", self._insert, add="+")
        lb.bind("<Tab>", self._insert, add="+")
        lb.bind("<Double-Button-1>", self._insert, add="+")
        lb.bind("<ButtonRelease-1>", self._insert, add="+")
        lb.bind("<Escape>", lambda e: (self.close() or "break"), add="+")

        # 호버 시 활성 항목 갱신
        def _on_motion(e):
            i = lb.nearest(e.y)
            if 0 <= i < lb.size():
                lb.activate(i)
                lb.selection_clear(0, tk.END)
                lb.selection_set(i)
        lb.bind("<Motion>", _on_motion, add="+")

        self.listbox = lb

        # 위치 설정 및 표시
        self.popup.update_idletasks()
        x, y = self._get_popup_position()
        self.popup.geometry(f"+{x}+{y}")
        self.popup.deiconify()

    def close(self):
        """드롭다운 닫기"""
        if self.popup and self.popup.winfo_exists():
            try:
                self.popup.destroy()
            except Exception:
                pass

        self.popup = None
        self.listbox = None
        self._current_word_start = None
        self._current_filter = ""
        self._is_filtering = False

def highlight_variables(widget: tk.Text) -> None:
    """Text 위젯에서 변수명 하이라이팅 (단순 변수명용)"""
    try:
        widget.tag_remove("var", "1.0", tk.END)
    except tk.TclError:
        return

    text = widget.get("1.0", "end-1c")

    # 단순 변수명 패턴 (알파벳/언더스코어로 시작, 알파벳/숫자/언더스코어 포함)
    var_pattern = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')

    for match in var_pattern.finditer(text):
        start_pos = f"1.0+{match.start()}c"
        end_pos = f"1.0+{match.end()}c"
        widget.tag_add("var", start_pos, end_pos)

    # 변수 스타일 설정
    widget.tag_configure("var", foreground="navy", font=("Consolas", 11, "bold"))


# ---------- 데이터 모델 ----------

@dataclass
class Choice:
    text: str
    target_id: str
    condition: Optional[str] = None

@dataclass
class Action:
    op: str  # e.g. 'set', 'add', 'sub', 'mul', 'div', 'floordiv', 'mod', 'pow'
    var: str
    value: Union[int, float, bool]

@dataclass
class Branch:
    branch_id: str
    title: str
    chapter_id: str
    paragraphs: List[str] = field(default_factory=list)
    choices: List[Choice] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)


@dataclass
class Chapter:
    chapter_id: str
    title: str
    branches: Dict[str, Branch] = field(default_factory=dict)

@dataclass
class Story:
    title: str = "Untitled"
    start_id: Optional[str] = None  # 시작 분기 ID
    ending_text: str = "The End"
    show_disabled: bool = False
    chapters: Dict[str, Chapter] = field(default_factory=dict)
    branches: Dict[str, Branch] = field(default_factory=dict)
    variables: Dict[str, Union[int, float, bool]] = field(default_factory=dict)

    def get_chapter(self, cid: str) -> Optional[Chapter]:
        return self.chapters.get(cid)

    def get_branch(self, bid: str) -> Optional[Branch]:
        return self.branches.get(bid)

    def ensure_unique_chapter_id(self, base: str = "chapter") -> str:
        i = 1
        cid = f"{base}"
        ids = set(self.chapters.keys())
        if cid not in ids:
            return cid
        while True:
            cid = f"{base}{i}"
            if cid not in ids:
                return cid
            i += 1

    def ensure_unique_branch_id(self, base: str = "branch") -> str:
        i = 1
        bid = f"{base}"
        ids = set(self.branches.keys())
        if bid not in ids:
            return bid
        while True:
            bid = f"{base}{i}"
            if bid not in ids:
                return bid
            i += 1

    def serialize(self) -> str:
        lines: List[str] = []
        lines.append(f"@title: {self.title}".rstrip())
        if self.start_id:
            lines.append(f"@start: {self.start_id}")
        lines.append(f"@ending: {self.ending_text}")
        if self.show_disabled:
            lines.append("@show-disabled: true")
        for var in sorted(self.variables.keys()):
            val = self.variables[var]
            val_str = str(val).lower() if isinstance(val, bool) else val
            lines.append(f"! {var} = {val_str}")
        lines.append("")

        for cid, ch in self.chapters.items():
            chap_header = f"@chapter {ch.chapter_id}: {ch.title}" if ch.title else f"@chapter {ch.chapter_id}"
            lines.append(chap_header)
            for bid, br in ch.branches.items():
                br_header = f"# {br.branch_id}: {br.title}" if br.title else f"# {br.branch_id}"
                lines.append(br_header)
                for p in br.paragraphs:
                    lines.append(p.rstrip())
                    lines.append("")
                op_map = {
                    "add": "+=",
                    "sub": "-=",
                    "mul": "*=",
                    "div": "/=",
                    "floordiv": "//=",
                    "mod": "%=",
                    "pow": "**=",
                }
                for act in br.actions:
                    if act.op == "set":
                        lines.append(f"! {act.var} = {act.value}")
                    else:
                        sym = op_map.get(act.op)
                        if sym:
                            lines.append(f"! {act.var} {sym} {act.value}")
                for c in br.choices:
                    if c.condition:
                        lines.append(f"* [{c.condition}] {c.text} -> {c.target_id}")
                    else:
                        lines.append(f"* {c.text} -> {c.target_id}")
                lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

# ---------- 파서 (열기용) ----------

class ParseError(Exception):
    pass

class StoryParser:
    def parse(self, text: str) -> Story:
        text = text.lstrip("\ufeff")
        lines = [ln.lstrip("\ufeff") for ln in text.splitlines()]
        story = Story()
        current_chapter: Optional[Chapter] = None
        current_branch: Optional[Branch] = None
        paragraph_buffer: List[str] = []

        # 메타데이터 처리
        for raw in lines:
            line = raw.strip()
            if line.startswith("@title:"):
                story.title = line[len("@title:"):].strip() or "Untitled"
                continue
            if line.startswith("@start:"):
                story.start_id = line[len("@start:"):].strip() or None
                continue
            if line.startswith("@ending:"):
                story.ending_text = line[len("@ending:"):].strip() or "The End"
                continue
            if line.startswith("@show-disabled:"):
                val = line[len("@show-disabled:"):].strip().lower()
                story.show_disabled = val in ("true", "1", "yes", "on")
                continue

        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip("\n")
            stripped = line.strip()
            i += 1

            if stripped.startswith(("@title:", "@start:", "@ending:", "@show-disabled:")):
                continue

            if stripped.startswith("@chapter"):
                current_branch = None
                current_chapter = self._parse_chapter_decl(stripped)
                if current_chapter.chapter_id in story.chapters:
                    raise ParseError(f"Duplicate chapter id: {current_chapter.chapter_id}")
                story.chapters[current_chapter.chapter_id] = current_chapter
                continue

            if stripped.startswith("#"):
                if current_chapter is None:
                    raise ParseError("Branch defined outside of a chapter.")
                if current_branch is not None and paragraph_buffer:
                    merged = self._merge_paragraph_buffer(paragraph_buffer)
                    current_branch.paragraphs.extend(merged)
                    paragraph_buffer.clear()
                current_branch = self._parse_branch_header(stripped, current_chapter.chapter_id)
                if current_branch.branch_id in story.branches:
                    raise ParseError(f"Duplicate branch id: {current_branch.branch_id}")
                story.branches[current_branch.branch_id] = current_branch
                current_chapter.branches[current_branch.branch_id] = current_branch
                continue

            if stripped == "":
                if current_branch is not None:
                    merged = self._merge_paragraph_buffer(paragraph_buffer)
                    current_branch.paragraphs.extend(merged)
                    paragraph_buffer.clear()
                continue

            if stripped.startswith("!"):
                action = self._parse_action_line(stripped)
                if current_branch is None:
                    if action.op != "set":
                        raise ParseError("State change found outside of any branch.")
                    story.variables[action.var] = action.value
                else:
                    current_branch.actions.append(action)
                continue

            if stripped.startswith("* "):
                if current_branch is None:
                    raise ParseError("Choice found outside of any branch.")
                choice = self._parse_choice_line(stripped)
                current_branch.choices.append(choice)
                continue

            if current_branch is None:
                raise ParseError("Found narrative text outside of a branch. Add a branch header starting with '#'.")
            paragraph_buffer.append(line)

        if current_branch is not None and paragraph_buffer:
            merged = self._merge_paragraph_buffer(paragraph_buffer)
            current_branch.paragraphs.extend(merged)
            paragraph_buffer.clear()

        if story.start_id is None:
            if story.branches:
                story.start_id = next(iter(story.branches.keys()))
            else:
                raise ParseError("No branches found in story.")
        return story

    def _merge_paragraph_buffer(self, buffer: List[str]) -> List[str]:
        if not buffer:
            return []
        paragraphs: List[str] = []
        current: List[str] = []
        for ln in buffer:
            if ln.strip() == "":
                if current:
                    paragraphs.append("\n".join(current).strip())
                    current = []
            else:
                current.append(ln)
        if current:
            paragraphs.append("\n".join(current).strip())
        return paragraphs

    def _parse_chapter_decl(self, line: str) -> Chapter:
        content = line[len("@chapter"):].strip()
        if ":" in content:
            cid, title = content.split(":", 1)
            return Chapter(chapter_id=cid.strip(), title=title.strip())
        return Chapter(chapter_id=content.strip(), title=content.strip())

    def _parse_branch_header(self, header_line: str, chapter_id: str) -> Branch:
        content = header_line.lstrip("#").strip()
        if ":" in content:
            bid, title = content.split(":", 1)
            return Branch(branch_id=bid.strip(), title=title.strip(), chapter_id=chapter_id)
        else:
            bid = content.strip()
            return Branch(branch_id=bid, title=bid, chapter_id=chapter_id)

    def _parse_choice_line(self, line: str) -> Choice:
        body = line[2:].strip()
        if "->" not in body:
            raise ParseError("Choice line must contain '->'.")
        left, right = body.split("->", 1)
        left = left.strip()
        condition: Optional[str] = None
        text: str
        if left.startswith("["):
            end = left.find("]")
            if end == -1:
                raise ParseError("Missing closing ']' in condition.")
            condition = left[1:end].strip()
            text = left[end + 1:].strip()
        else:
            text = left
        target = right.strip()
        if not text or not target:
            raise ParseError("Choice text or target is empty.")
        return Choice(text=text, target_id=target, condition=condition)

    def _parse_action_line(self, line: str) -> Action:
        content = line[1:].strip()
        if content.startswith("set "):
            rest = content[4:].strip()
            if "=" not in rest:
                raise ParseError("Invalid set syntax.")
            var, val = rest.split("=", 1)
            return Action(op="set", var=var.strip(), value=self._parse_value(val.strip()))
        if content.startswith("add "):
            rest = content[4:].strip()
            if "+=" not in rest:
                raise ParseError("Invalid add syntax.")
            var, val = rest.split("+=", 1)
            return Action(op="add", var=var.strip(), value=self._parse_value(val.strip()))
        m = re.match(r"(\w+)\s*(=|\+=|-=|\*=|/=|//=|%=|\*\*=)\s*(.+)", content)
        if m:
            var, op, val = m.groups()
            op_map = {
                "=": "set",
                "+=": "add",
                "-=": "sub",
                "*=": "mul",
                "/=": "div",
                "//=": "floordiv",
                "%=": "mod",
                "**=": "pow",
            }
            return Action(op=op_map[op], var=var.strip(), value=self._parse_value(val.strip()))
        raise ParseError("Unknown action command.")

    def _parse_value(self, token: str) -> Union[int, float, bool]:
        t = token.lower()
        if t == "true":
            return True
        if t == "false":
            return False
        try:
            return int(token)
        except ValueError:
            try:
                return float(token)
            except ValueError:
                raise ParseError(f"Invalid value: {token}")

# ---------- 실행기 (미리보기용) ----------

@dataclass
class Step:
    """
    히스토리의 한 단계. 분기(branch_id)와 그 때 사용자가 선택한 텍스트를 기록.
    선택지가 없는 분기일 수도 있으므로 chosen_text는 Optional.
    """
    branch_id: str
    chosen_text: Optional[str] = None


class BranchingNovelApp(tk.Tk):
    """
    Tkinter 기반 GUI 애플리케이션
    """

    def __init__(self, story: Story, file_path: str, show_disabled: bool = False):
        super().__init__()
        self.title(f"{story.title} - Branching Novel")
        self.geometry("1000x700")

        self.story = story
        self.file_path = file_path

        # 상태 값과 옵션
        self.show_disabled = show_disabled
        self.state: Dict[str, Union[int, float, bool]] = {}

        # 히스토리와 현재 인덱스
        self.history: List[Step] = []
        self.current_index: int = -1  # history에서 현재 분기 위치
        self.visited_chapters: List[str] = []
        self.chapter_positions: List[int] = []  # 각 챕터의 시작 인덱스
        self.chapter_page_index: int = -1

        self._build_ui()
        self._bind_events()

        # 시작 챕터로 이동
        self._reset_to_start()

    def _build_ui(self):
        # 전체 수직 레이아웃: 좌측 챕터 리스트, 우측 본문/선택/네비
        self.columnconfigure(0, weight=0)  # left panel width fixed
        self.columnconfigure(1, weight=1)  # right panel expands
        self.rowconfigure(0, weight=1)

        # 좌측: 챕터 리스트 패널
        left_frame = ttk.Frame(self, padding=(8, 8, 8, 8))
        left_frame.grid(row=0, column=0, sticky="nsw")
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        ttk.Label(left_frame, text="Chapters", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.chapter_list = tk.Listbox(left_frame, exportselection=False, height=25)
        self.chapter_list.grid(row=1, column=0, sticky="nsw")
        # 사용자 클릭/포커스 방지
        self.chapter_list.configure(state="disabled", takefocus=0)
        self._populate_chapter_list()

        # 우측: 상단 네비게이션 바
        right_frame = ttk.Frame(self, padding=(8, 8, 8, 8))
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(2, weight=1)

        nav_frame = ttk.Frame(right_frame)
        nav_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        nav_frame.columnconfigure(1, weight=1)

        self.title_label = ttk.Label(nav_frame, text=self.story.title, font=("Segoe UI", 12, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")

        self.path_label = ttk.Label(nav_frame, text="", foreground="#666666")
        self.path_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        btn_frame = ttk.Frame(nav_frame)
        btn_frame.grid(row=0, column=1, rowspan=2, sticky="e")

        self.btn_home = ttk.Button(btn_frame, text=tr("start_over"), command=self._confirm_reset)
        self.btn_home.grid(row=0, column=0, padx=4)
        self.btn_prev = ttk.Button(btn_frame, text="←", command=self._go_prev_chapter)
        self.btn_prev.grid(row=0, column=1, padx=4)
        self.btn_next = ttk.Button(btn_frame, text="→", command=self._go_next_chapter)
        self.btn_next.grid(row=0, column=2, padx=4)

        # 본문 표시
        text_frame = ttk.Frame(right_frame)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.text_widget = tk.Text(
            text_frame, wrap="word", state="disabled", relief="flat",
            font=("Malgun Gothic", 12) if sys.platform.startswith("win") else ("Noto Sans CJK KR", 12)
        )
        self.text_widget.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_widget.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text_widget.configure(yscrollcommand=scroll.set)

        # 선택지 영역
        self.choice_frame = ttk.Frame(right_frame)
        self.choice_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.choice_frame.columnconfigure(0, weight=1)

        self._update_nav_buttons()

    def _bind_events(self):
        self.bind("<Left>", self._go_prev_chapter)
        self.bind("<Right>", self._go_next_chapter)

    def _populate_chapter_list(self):
        # 리스트 업데이트 시 일시적으로 활성화
        self.chapter_list.configure(state="normal")
        self.chapter_list.delete(0, tk.END)
        for cid in self.visited_chapters:
            ch = self.story.get_chapter(cid)
            title = ch.title if ch and ch.title else cid
            self.chapter_list.insert(tk.END, title)
        self.chapter_list.configure(state="disabled")

    def _go_prev_chapter(self, event=None):
        if self.chapter_page_index > 0:
            self.chapter_page_index -= 1
            self._render_page(self.chapter_page_index)

    def _go_next_chapter(self, event=None):
        if self.chapter_page_index < len(self.chapter_positions) - 1:
            self.chapter_page_index += 1
            self._render_page(self.chapter_page_index)

    def _confirm_reset(self):
        if messagebox.askyesno(
            tr("warning"), tr("reset_warning")
        ):
            self._reset_to_start()

    def _reset_to_start(self):
        self.history.clear()
        self.current_index = -1
        self.visited_chapters.clear()
        self.chapter_positions.clear()
        self.chapter_page_index = -1
        self._populate_chapter_list()
        start_id = self.story.start_id
        if not start_id or start_id not in self.story.branches:
            messagebox.showerror(tr("error"), tr("invalid_start"))
            return
        self._append_step(Step(branch_id=start_id, chosen_text=None), truncate_future=False)
        self._render_current()

    def _append_step(self, step: Step, truncate_future: bool = True):
        # 과거로 돌아간 상태에서 새 선택을 하면 미래 히스토리를 잘라낸다.
        if truncate_future and self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        prev_branch = self.story.get_branch(self.history[self.current_index].branch_id) if self.history and self.current_index >= 0 else None
        new_branch = self.story.get_branch(step.branch_id)
        self.history.append(step)
        self.current_index = len(self.history) - 1
        if not self.chapter_positions:
            self.chapter_positions.append(0)
        elif prev_branch and new_branch and prev_branch.chapter_id != new_branch.chapter_id:
            self.chapter_positions.append(self.current_index)
        self.chapter_page_index = len(self.chapter_positions) - 1
        if new_branch:
            self._record_visit(new_branch.chapter_id)
        self._update_nav_buttons()

    def _replace_current_step(self, step: Step):
        if 0 <= self.current_index < len(self.history):
            self.history[self.current_index] = step
        else:
            self.history = [step]
            self.current_index = 0
        br = self.story.get_branch(step.branch_id)
        if br:
            self._record_visit(br.chapter_id)
        self._update_nav_buttons()

    def _record_visit(self, chapter_id: str):
        # chapter_id를 직접 받아 목록에 추가/선택한다.
        if not chapter_id:
            return
        if chapter_id not in self.visited_chapters:
            self.visited_chapters.append(chapter_id)
            self._populate_chapter_list()
        self._select_chapter_in_list(chapter_id)

    def _render_page(self, page_index: int):
        if not self.chapter_positions:
            return
        start = self.chapter_positions[page_index]
        end = self.chapter_positions[page_index + 1] if page_index + 1 < len(self.chapter_positions) else len(self.history)
        lines: List[str] = []
        if start > 0:
            prev_step = self.history[start - 1]
            if prev_step.chosen_text:
                lines.append(f"> {prev_step.chosen_text}")
        for i in range(start, end):
            step = self.history[i]
            br = self.story.get_branch(step.branch_id)
            if not br:
                continue
            if br.paragraphs:
                lines.append("\n".join(br.paragraphs))
            if i + 1 < end and step.chosen_text:
                lines.append(f"> {step.chosen_text}")
        text = "\n".join(lines)
        if not text:
            text = tr("no_content")
        self._set_text_content(text)
        if page_index == len(self.chapter_positions) - 1:
            last_branch = self.story.get_branch(self.history[end - 1].branch_id)
            if last_branch:
                self._render_choices(last_branch)
        else:
            for w in self.choice_frame.winfo_children():
                w.destroy()
        self._update_path_label()
        cur_branch = self.story.get_branch(self.history[start].branch_id)
        if cur_branch:
            self._select_chapter_in_list(cur_branch.chapter_id)
        self._update_nav_buttons()

    def _render_current(self):
        if not self.history:
            return
        self.state = self._compute_state(self.current_index)
        self._render_page(self.chapter_page_index)

    def _current_branch(self) -> Optional[Branch]:
        if 0 <= self.current_index < len(self.history):
            step = self.history[self.current_index]
            return self.story.get_branch(step.branch_id)
        return None

    def _set_text_content(self, text: str):
        self.text_widget.configure(state="normal")
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, text)
        self.text_widget.configure(state="disabled")
        self.text_widget.see(tk.END)

    def _render_choices(self, br: Branch):
        # 기존 버튼 제거
        for w in self.choice_frame.winfo_children():
            w.destroy()

        display: List[Tuple[Choice, bool]] = []  # (choice, disabled)
        for choice in br.choices:
            ok = True
            if choice.condition:
                ok = self._evaluate_condition(choice.condition)
            if ok:
                display.append((choice, False))
            elif self.show_disabled:
                display.append((choice, True))

        if not display or all(disabled for _, disabled in display):
            lbl = ttk.Label(self.choice_frame, text=self.story.ending_text)
            lbl.grid(row=0, column=0, sticky="w")
            exit_btn = ttk.Button(self.choice_frame, text=tr("exit"), command=self.destroy)
            exit_btn.grid(row=1, column=0, sticky="ew", pady=2)
            return

        # 버튼 생성
        for idx, (choice, disabled) in enumerate(display, 1):
            btn = ttk.Button(self.choice_frame, text=f"{idx}. {choice.text}",
                             command=lambda c=choice: self._choose(c))
            if disabled:
                btn.state(["disabled"])
            btn.grid(row=idx-1, column=0, sticky="ew", pady=2)

    def _choose(self, choice: Choice):
        # 타겟 분기 유효성 검사
        target = self.story.get_branch(choice.target_id)
        if not target:
            messagebox.showerror(tr("error"), tr("missing_target", id=choice.target_id))
            return

        # 현재 스텝에 선택 텍스트 기록
        if 0 <= self.current_index < len(self.history):
            cur = self.history[self.current_index]
            cur.chosen_text = choice.text
            self.history[self.current_index] = cur

        # 미래 히스토리 절단 후 다음 스텝 추가
        next_step = Step(branch_id=choice.target_id, chosen_text=None)
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        self._append_step(next_step, truncate_future=False)
        self._render_current()

    def _update_nav_buttons(self):
        # 현재 페이지 위치에 따라 네비게이션 버튼 상태 업데이트
        if self.chapter_page_index <= 0:
            self.btn_prev.state(["disabled"])
        else:
            self.btn_prev.state(["!disabled"])

        if self.chapter_page_index >= len(self.chapter_positions) - 1:
            self.btn_next.state(["disabled"])
        else:
            self.btn_next.state(["!disabled"])

    def _update_path_label(self):
        # 경로를 간단히 요약하여 표시: id(선택) -> id(선택) ...
        parts: List[str] = []
        for i, step in enumerate(self.history):
            br = self.story.get_branch(step.branch_id)
            name = br.title if br and br.title else step.branch_id
            if step.chosen_text:
                parts.append(f"{name}({step.chosen_text})")
            else:
                parts.append(f"{name}")
        self.path_label.configure(text=" → ".join(parts))

    def _select_chapter_in_list(self, cid: str):
        # 리스트에서 해당 id가 있는 항목 선택
        state = self.chapter_list.cget("state")
        self.chapter_list.configure(state="normal")
        for i in range(self.chapter_list.size()):
            item = self.chapter_list.get(i)
            item_cid = item.split("|", 1)[0].strip()
            if item_cid == cid:
                self.chapter_list.selection_clear(0, tk.END)
                self.chapter_list.selection_set(i)
                self.chapter_list.see(i)
                break
        self.chapter_list.configure(state=state)

    def _compute_state(self, upto_index: int) -> Dict[str, Union[int, float, bool]]:
        state: Dict[str, Union[int, float, bool]] = dict(self.story.variables)
        for i in range(0, upto_index + 1):
            step = self.history[i]
            br = self.story.get_branch(step.branch_id)
            if not br:
                continue
            for act in br.actions:
                cur = state.get(act.var, 0)
                if isinstance(cur, bool):
                    cur = int(cur)
                val = act.value
                if isinstance(val, bool):
                    val = int(val)
                if act.op == "set":
                    state[act.var] = val
                elif act.op == "add":
                    state[act.var] = cur + val
                elif act.op == "sub":
                    state[act.var] = cur - val
                elif act.op == "mul":
                    state[act.var] = cur * val
                elif act.op == "div":
                    state[act.var] = cur / val
                elif act.op == "floordiv":
                    state[act.var] = cur // val
                elif act.op == "mod":
                    state[act.var] = cur % val
                elif act.op == "pow":
                    state[act.var] = cur ** val
        return state

    def _evaluate_condition(self, cond: str) -> bool:
        expr = self._to_python_expr(cond)

        try:
            # 순수 표현식으로 파싱
            tree = ast.parse(expr, mode="eval")  # Expression 노드
            result = self._eval_ast(tree)
            return bool(result)
        except Exception:
            # 어떤 이유로든 실패하면 False
            return False

    def _eval_ast(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body)

        if isinstance(node, ast.Module):
            # exec 모드 대비: 남아있을 가능성에 대응
            result = None
            for stmt in node.body:
                result = self._eval_ast(stmt)
            return result

        if isinstance(node, ast.Expr):
            return self._eval_ast(node.value)

        # 할당은 조건식에서 거의 안 쓰지만 지원 유지
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("Unsupported assignment")
            val = self._eval_ast(node.value)
            self.state[node.targets[0].id] = val
            return val

        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise ValueError("Unsupported assignment")
            target = node.target.id
            cur = self.state.get(target, 0)
            if isinstance(cur, bool):
                cur = int(cur)
            val = self._eval_ast(node.value)
            if isinstance(val, bool):
                val = int(val)
            if isinstance(node.op, ast.Add):
                self.state[target] = cur + val
            elif isinstance(node.op, ast.Sub):
                self.state[target] = cur - val
            elif isinstance(node.op, ast.Mult):
                self.state[target] = cur * val
            elif isinstance(node.op, ast.Div):
                self.state[target] = cur / val
            elif isinstance(node.op, ast.FloorDiv):
                self.state[target] = cur // val
            elif isinstance(node.op, ast.Mod):
                self.state[target] = cur % val
            elif isinstance(node.op, ast.Pow):
                self.state[target] = cur ** val
            else:
                raise ValueError("Unsupported aug assignment")
            return self.state[target]

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for v in node.values:
                    if not self._eval_ast(v):
                        return False
                return True
            if isinstance(node.op, ast.Or):
                for v in node.values:
                    if self._eval_ast(v):
                        return True
                return False
            raise ValueError("Unsupported boolean operator")

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_ast(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError("Unsupported unary operator")

        if isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError("Unsupported binary operator")

        if isinstance(node, ast.Compare):
            left = self._eval_ast(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval_ast(comp)
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                else:
                    raise ValueError("Unsupported comparison operator")
                if not ok:
                    return False
                left = right
            return True

        if isinstance(node, ast.Name):
            return self.state.get(node.id, 0)

        if isinstance(node, ast.Constant):
            return node.value

        # 안전을 위해 기타 노드는 허용하지 않음
        raise ValueError(f"Unsupported expression: {type(node).__name__}")

    def _to_python_expr(self, cond: str) -> str:
        # 공백 정리
        s = cond.strip()

        # 우선순위: '!=' → 그대로, 그 외 '!' → ' not '
        out = []
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == '!':
                if i + 1 < len(s) and s[i + 1] == '=':
                    out.append('!=')
                    i += 2
                else:
                    # 식의 맨 앞에서 공백이 생겨도 strip으로 제거
                    out.append(' not ')
                    i += 1
            elif ch == '&':
                if i + 1 < len(s) and s[i + 1] == '&':
                    out.append(' and ')
                    i += 2
                else:
                    out.append(' and ')
                    i += 1
            elif ch == '|':
                if i + 1 < len(s) and s[i + 1] == '|':
                    out.append(' or ')
                    i += 2
                else:
                    out.append(' or ')
                    i += 1
            else:
                out.append(ch)
                i += 1

        expr = ''.join(out)

        # true/false 대소문자 혼용 대응
        expr = re.sub(r"\btrue\b", "True", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bfalse\b", "False", expr, flags=re.IGNORECASE)

        # ★ 핵심 수정: 선행/후행 공백 제거로 IndentationError 방지
        return expr.strip()


# ---------- 에디터 GUI ----------

class ConditionRowDialog(tk.Toplevel):
    def __init__(self, master, variables: List[str], initial: Optional[Tuple[str, str, str]]):
        super().__init__(master)
        self.title(tr("condition_action_title"))
        self.resizable(False, False)
        self.result_ok = False
        self.condition: Optional[Tuple[str, str, str]] = None

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text=tr("variable")).grid(row=0, column=0, sticky="w")
        self.cmb_var = ttk.Combobox(frm, values=variables, state="readonly", width=20)
        self.cmb_var.grid(row=1, column=0, sticky="ew", pady=(0,8))

        ttk.Label(frm, text=tr("operator")).grid(row=0, column=1, sticky="w", padx=(8,0))
        ops = ["==", "!=", ">", "<", ">=", "<=", "=", "+=", "-=", "*=", "/=", "//=", "%=", "**="]
        self.cmb_op = ttk.Combobox(frm, values=ops, state="readonly", width=7)
        self.cmb_op.grid(row=1, column=1, sticky="w", padx=(8,0))

        ttk.Label(frm, text=tr("value")).grid(row=0, column=2, sticky="w", padx=(8,0))
        self.ent_val = ttk.Entry(frm, width=15)
        self.ent_val.grid(row=1, column=2, sticky="ew", padx=(8,0))

        ttk.Label(frm, text=tr("operator_help"), justify="left").grid(row=2, column=0, columnspan=3, sticky="w", pady=(8,0))

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=3, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text=tr("ok"), command=self._ok)
        cancel = ttk.Button(btns, text=tr("cancel"), command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        if initial:
            var, op, val = initial
            vals = list(self.cmb_var["values"])
            if var not in vals:
                vals.append(var)
                self.cmb_var["values"] = vals
            self.cmb_var.set(var)
            self.cmb_op.set(op)
            self.ent_val.insert(0, val)
        else:
            if variables:
                self.cmb_var.current(0)
                self.cmb_op.current(0)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        self.cmb_var.focus_set()
        self.wait_window(self)

    def _ok(self):
        var = self.cmb_var.get().strip()
        op = self.cmb_op.get().strip()
        val = self.ent_val.get().strip()
        if not var or not op or not val:
            messagebox.showerror(tr("error"), tr("input_values_required"))
            return
        self.condition = (var, op, val)
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()


class VariableDialog(tk.Toplevel):
    def __init__(self, master, name: str = "", value: Optional[Union[int, float, bool]] = None):
        super().__init__(master)
        self.title(tr("add_variable") if not name else tr("edit_variable"))
        self.resizable(False, False)
        self.result_ok = False
        self.var_name: str = name
        self.value: Union[int, float, bool] = value if value is not None else 0

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text=tr("variable_name")).grid(row=0, column=0, sticky="w")
        self.ent_name = ttk.Entry(frm, width=20)
        self.ent_name.grid(row=1, column=0, sticky="ew", pady=(0,8))
        if name:
            self.ent_name.insert(0, name)

        ttk.Label(frm, text=tr("initial_value")).grid(row=0, column=1, sticky="w", padx=(8,0))
        self.ent_val = ttk.Entry(frm, width=10)
        self.ent_val.grid(row=1, column=1, sticky="ew", padx=(8,0))
        if value is not None:
            self.ent_val.insert(0, str(value).lower() if isinstance(value, bool) else str(value))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text=tr("ok"), command=self._ok)
        cancel = ttk.Button(btns, text=tr("cancel"), command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        self.ent_name.focus_set()
        self.wait_window(self)

    def _ok(self):
        name = self.ent_name.get().strip()
        val_text = self.ent_val.get().strip()
        if not name or not val_text:
            messagebox.showerror(tr("error"), tr("input_var_init_required"))
            return
        if val_text.lower() == "true":
            val: Union[int, float, bool] = True
        elif val_text.lower() == "false":
            val = False
        else:
            try:
                val = int(val_text)
            except ValueError:
                try:
                    val = float(val_text)
                except ValueError:
                    messagebox.showerror(tr("error"), tr("invalid_initial_value"))
                    return
        self.var_name = name
        self.value = val
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()


class ConditionDialog(tk.Toplevel):
    def __init__(self, master, variables: List[str], initial: str, story: Story):
        super().__init__(master)
        self.title(tr("edit_conditions"))
        self.resizable(False, False)
        self.result_ok = False
        self.variables = variables
        self.story = story
        self.conditions: List[Tuple[str, str, str]] = self._parse_initial(initial)

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frm, columns=("var", "op", "val"), show="headings", height=6)
        self.tree.heading("var", text=tr("variable"))
        self.tree.heading("op", text=tr("operator"))
        self.tree.heading("val", text=tr("value"))
        self.tree.column("var", width=100, anchor="w")
        self.tree.column("op", width=80, anchor="w")
        self.tree.column("val", width=120, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        btns = ttk.Frame(frm)
        btns.grid(row=0, column=1, sticky="ns", padx=(8,0))
        ttk.Button(btns, text=tr("add"), command=self._add).grid(row=0, column=0, pady=2)
        ttk.Button(btns, text=tr("edit"), command=self._edit).grid(row=1, column=0, pady=2)
        ttk.Button(btns, text=tr("delete"), command=self._delete).grid(row=2, column=0, pady=2)
        ttk.Button(btns, text=tr("add_variable"), command=self._add_variable).grid(row=3, column=0, pady=2)

        bottom = ttk.Frame(frm)
        bottom.grid(row=1, column=0, columnspan=2, sticky="e", pady=(8,0))
        ok = ttk.Button(bottom, text=tr("ok"), command=self._ok)
        cancel = ttk.Button(bottom, text=tr("cancel"), command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        self._refresh_tree()

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        self.tree.focus_set()
        self.wait_window(self)

    def _parse_initial(self, expr: str) -> List[Tuple[str, str, str]]:
        conds: List[Tuple[str, str, str]] = []
        if not expr:
            return conds
        parts = re.split(r"\s+and\s+", expr)
        for part in parts:
            m = re.match(r"\s*(\w+)\s*(==|!=|>=|<=|>|<|=|\+=|-=|\*=|/=|//=|%=|\*\*=)\s*(.+)\s*", part)
            if m:
                conds.append((m.group(1), m.group(2), m.group(3)))
        return conds

    def _refresh_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for var, op, val in self.conditions:
            self.tree.insert("", tk.END, values=(var, op, val))

    def _add(self):
        dlg = ConditionRowDialog(self, self.variables, None)
        if dlg.result_ok and dlg.condition:
            self.conditions.append(dlg.condition)
            self._refresh_tree()

    def _edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        dlg = ConditionRowDialog(self, self.variables, self.conditions[idx])
        if dlg.result_ok and dlg.condition:
            self.conditions[idx] = dlg.condition
            self._refresh_tree()

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        self.conditions.pop(idx)
        self._refresh_tree()

    def _add_variable(self):
        dlg = VariableDialog(self)
        if dlg.result_ok:
            self.story.variables[dlg.var_name] = dlg.value
            if dlg.var_name not in self.variables:
                self.variables.append(dlg.var_name)
            editor = self.master.master
            editor._set_dirty(True)
            editor._refresh_variable_list()
            editor._update_preview()

    def _ok(self):
        self.condition_str = " and ".join(f"{v} {op} {val}" for v, op, val in self.conditions)
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()


class ChoiceEditor(tk.Toplevel):
    def __init__(self, master, title: str, choice: Optional[Choice], branch_ids: List[str], variables: List[str]):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.choice: Optional[Choice] = None
        self.result_ok = False
        self.variables = variables

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)

        ttk.Label(frm, text=tr("button_text")).grid(row=0, column=0, sticky="w")
        self.ent_text = tk.Text(frm, width=50, height=1, wrap="none")
        self.ent_text.grid(row=1, column=0, sticky="ew", pady=(0,8))
        self.auto_text = VarAutocomplete(self.ent_text, lambda: self.variables)
        self.ent_text.bind("<KeyRelease>", lambda e: highlight_variables(self.ent_text))
        highlight_variables(self.ent_text)
        ttk.Button(frm, text="$", width=2, command=self.auto_text.trigger).grid(row=1, column=1, padx=(4,0))

        ttk.Label(frm, text=tr("target_branch_id")).grid(row=2, column=0, sticky="w")
        self.cmb_target = ttk.Combobox(frm, values=branch_ids, state="readonly", width=30)
        self.cmb_target.grid(row=3, column=0, sticky="w")

        ttk.Label(frm, text=tr("condition_action_expr")).grid(row=4, column=0, sticky="w")
        cond_frame = ttk.Frame(frm)
        cond_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0,8))
        cond_frame.columnconfigure(0, weight=1)
        self.ent_cond = ttk.Entry(cond_frame, width=50, state="readonly")
        self.ent_cond.grid(row=0, column=0, sticky="ew")
        ttk.Button(cond_frame, text=tr("edit_ellipsis"), command=self._open_cond_editor).grid(row=0, column=1, padx=(4,0))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text=tr("ok"), command=self._ok)
        cancel = ttk.Button(btns, text=tr("cancel"), command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        if choice:
            self.ent_text.insert("1.0", choice.text)
            highlight_variables(self.ent_text)
            vals = list(self.cmb_target["values"])
            if choice.target_id not in vals:
                vals.append(choice.target_id)
                self.cmb_target["values"] = vals
            self.cmb_target.set(choice.target_id)
            if choice.condition:
                self.ent_cond.configure(state="normal")
                self.ent_cond.delete(0, tk.END)
                self.ent_cond.insert(0, choice.condition)
                self.ent_cond.configure(state="readonly")
        else:
            if branch_ids:
                self.cmb_target.current(0)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        self.ent_text.focus_set()
        self.wait_window(self)

    def _ok(self):
        text = self.ent_text.get("1.0", "end-1c").strip()
        target = self.cmb_target.get().strip()
        cond = self.ent_cond.get().strip()
        cond = re.sub(r"\btrue\b", "1", cond, flags=re.IGNORECASE)
        cond = re.sub(r"\bfalse\b", "0", cond, flags=re.IGNORECASE)
        if not text:
            messagebox.showerror(tr("error"), tr("input_button_text"))
            return
        if not target:
            messagebox.showerror(tr("error"), tr("select_target_branch"))
            return
        self.choice = Choice(text=text, target_id=target, condition=(cond or None))
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()

    def _open_cond_editor(self):
        dlg = ConditionDialog(self, self.variables, self.ent_cond.get().strip(), self.master.story)
        if dlg.result_ok:
            self.ent_cond.configure(state="normal")
            self.ent_cond.delete(0, tk.END)
            self.ent_cond.insert(0, dlg.condition_str)
            self.ent_cond.configure(state="readonly")
            self.variables = sorted(set(self.variables) | set(self.master.story.variables.keys()))

class ChapterEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Branching Novel Editor")
        self.geometry("1200x800")
        self.minsize(1000, 700)

        self.story = Story()
        # 초기 챕터와 분기 생성
        ch_id = self.story.ensure_unique_chapter_id("chapter")
        chapter = Chapter(chapter_id=ch_id, title="Chapter 1")
        self.story.chapters[ch_id] = chapter
        br_id = self.story.ensure_unique_branch_id("intro")
        branch = Branch(branch_id=br_id, title="Introduction", chapter_id=ch_id)
        chapter.branches[br_id] = branch
        self.story.branches[br_id] = branch
        self.story.start_id = br_id

        self.current_chapter_id: Optional[str] = ch_id
        self.current_branch_id: Optional[str] = br_id
        self.current_file: Optional[str] = None
        self.dirty: bool = False
        self.preview_modified: bool = False
        self._preview_updating: bool = False

        self._build_menu()
        self._build_ui()
        self._refresh_chapter_list()
        # initialize editor with the first chapter
        self._load_chapter_to_form(ch_id)
        self._refresh_meta_panel()
        self._update_preview()

        # 찾기/변경 상태
        self.find_results: List[Tuple[str, int]] = []
        self.find_index: int = -1
        self._last_find_text: str = ""
        self._last_find_scope: str = "branch"

        # 창 닫힘 이벤트에 종료 처리 연결
        self.protocol("WM_DELETE_WINDOW", self._exit_app)

    # ---------- UI 구성 ----------
    def _build_menu(self):
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label=tr("new"), command=self._new_story, accelerator="Ctrl+N")
        fm.add_command(label=tr("open"), command=self._open_file, accelerator="Ctrl+O")
        fm.add_separator()
        fm.add_command(label=tr("save"), command=self._save_file, accelerator="Ctrl+S")
        fm.add_command(label=tr("save_as"), command=self._save_file_as)
        fm.add_separator()
        fm.add_command(label=tr("exit"), command=self._exit_app)
        m.add_cascade(label=tr("file_menu"), menu=fm)

        em = tk.Menu(m, tearoff=0)
        em.add_command(label=tr("add_chapter"), command=self._add_chapter, accelerator="Ctrl+Shift+A")
        em.add_command(label=tr("delete_chapter"), command=self._delete_current_chapter, accelerator="Del")
        em.add_separator()
        em.add_command(label=tr("find_replace"), command=self._open_find_window, accelerator="Ctrl+F")
        m.add_cascade(label=tr("edit_menu"), menu=em)

        self.config(menu=m)

        self.bind_all("<Control-n>", lambda e: self._new_story())
        self.bind_all("<Control-o>", lambda e: self._open_file())
        self.bind_all("<Control-s>", lambda e: self._save_file())
        self.bind_all("<Delete>", lambda e: self._delete_current_chapter())
        self.bind_all("<Control-Shift-A>", lambda e: self._add_chapter())
        self.bind_all("<Control-f>", lambda e: self._open_find_window())

    def _build_ui(self):
        # 좌: 메타 + 챕터 리스트, 우: 챕터 편집 + 선택지 + 미리보기
        root = ttk.Frame(self, padding=8)

        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        left.rowconfigure(2, weight=1)
        left.rowconfigure(3, weight=1)

        # 작품 메타
        meta = ttk.LabelFrame(left, text=tr("story_info"), padding=8)
        meta.grid(row=0, column=0, sticky="ew")
        meta.columnconfigure(1, weight=1)

        ttk.Label(meta, text=tr("title_label")).grid(row=0, column=0, sticky="w")
        self.ent_title = tk.Text(meta, width=30, height=1, wrap="none")
        self.ent_title.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        self.ent_title.insert("1.0", self.story.title)
        self.ent_title.bind(
            "<KeyRelease>",
            lambda e: (self._on_title_changed(), highlight_variables(self.ent_title)),
        )
        self.auto_title = VarAutocomplete(self.ent_title, lambda: self._collect_variables())
        highlight_variables(self.ent_title)
        ttk.Button(meta, text="$", width=2, command=self.auto_title.trigger).grid(row=0, column=2, padx=(4, 0))

        ttk.Label(meta, text=tr("start_branch_label")).grid(row=1, column=0, sticky="w")
        self.cmb_start = ttk.Combobox(meta, values=[], state="readonly")
        self.cmb_start.grid(row=1, column=1, sticky="ew")
        self.cmb_start.bind("<<ComboboxSelected>>", lambda e: self._on_start_changed())

        ttk.Label(meta, text=tr("ending_text_label")).grid(row=2, column=0, sticky="w")
        self.ent_end = ttk.Entry(meta, width=30)
        self.ent_end.grid(row=2, column=1, sticky="ew")
        self.ent_end.insert(0, self.story.ending_text)
        self.ent_end.bind("<KeyRelease>", lambda e: self._on_ending_changed())
        self.auto_end = VarAutocomplete(self.ent_end, lambda: self._collect_variables())
        ttk.Button(meta, text="$", width=2, command=self.auto_end.trigger).grid(row=2, column=2, padx=(4, 0))

        self.var_show_disabled = tk.BooleanVar(value=self.story.show_disabled)
        self.chk_show_disabled = ttk.Checkbutton(
            meta,
            text=tr("show_disabled_choices"),
            variable=self.var_show_disabled,
            command=self._on_show_disabled_changed,
        )
        self.chk_show_disabled.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # 변수 목록
        var_frame = ttk.LabelFrame(left, text=tr("variable_list"), padding=8)
        var_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        var_frame.columnconfigure(0, weight=1)

        btns = ttk.Frame(var_frame)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text=tr("add"), command=self._add_variable).pack(side="left")
        ttk.Button(btns, text=tr("edit"), command=self._edit_variable).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text=tr("delete"), command=self._delete_variable).pack(side="left", padx=(6, 0))

        self.tree_vars = ttk.Treeview(var_frame, columns=("var", "val"), show="headings", height=5)
        self.tree_vars.heading("var", text=tr("variable"))
        self.tree_vars.heading("val", text=tr("value"))
        self.tree_vars.column("var", width=80, anchor="w")
        self.tree_vars.column("val", width=80, anchor="w")
        self.tree_vars.grid(row=1, column=0, sticky="ew")

        # 챕터 목록
        chap_frame = ttk.LabelFrame(left, text=tr("chapter_list"), padding=8)
        chap_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        chap_frame.rowconfigure(1, weight=1)
        chap_frame.columnconfigure(0, weight=1)

        self.lst_chapters = tk.Listbox(chap_frame, height=20, exportselection=False)
        self.lst_chapters.grid(row=1, column=0, sticky="nsew")
        self.lst_chapters.bind("<<ListboxSelect>>", lambda e: self._on_select_chapter())
        self.lst_chapters.bind("<Double-Button-1>", lambda e: self._on_select_chapter())

        btns = ttk.Frame(chap_frame)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text=tr("add"), command=self._add_chapter).pack(side="left")
        ttk.Button(btns, text=tr("delete"), command=self._delete_current_chapter).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text=tr("up"), command=lambda: self._reorder_chapter(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text=tr("down"), command=lambda: self._reorder_chapter(1)).pack(side="left", padx=(6, 0))

        # 분기 목록
        branch_frame = ttk.LabelFrame(left, text=tr("branch_list"), padding=8)
        branch_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        branch_frame.rowconfigure(1, weight=1)
        branch_frame.columnconfigure(0, weight=1)

        self.lst_branches = tk.Listbox(branch_frame, height=15, exportselection=False)
        self.lst_branches.grid(row=1, column=0, sticky="nsew")
        self.lst_branches.bind("<<ListboxSelect>>", lambda e: self._on_select_branch())
        self.lst_branches.bind("<Double-Button-1>", lambda e: self._on_select_branch())

        bbtns = ttk.Frame(branch_frame)
        bbtns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bbtns, text=tr("add"), command=self._add_branch).pack(side="left")
        ttk.Button(bbtns, text=tr("delete"), command=self._delete_current_branch).pack(side="left", padx=(6, 0))
        ttk.Button(bbtns, text=tr("up"), command=lambda: self._reorder_branch(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(bbtns, text=tr("down"), command=lambda: self._reorder_branch(1)).pack(side="left", padx=(6, 0))

        # 우측 편집/미리보기 영역
        right = ttk.Notebook(root)
        right.grid(row=0, column=1, sticky="nsew")
        self.nb_right = right

        # 챕터 편집 탭
        edit_tab = ttk.Frame(right, padding=8)
        right.add(edit_tab, text=tr("edit_branch_tab"))

        edit_tab.columnconfigure(1, weight=1)
        edit_tab.rowconfigure(4, weight=1)

        ttk.Label(edit_tab, text=tr("chapter_id")).grid(row=0, column=0, sticky="w")
        self.ent_ch_id = ttk.Entry(edit_tab)
        self.ent_ch_id.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        self.ent_ch_id.bind("<FocusOut>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_id.bind("<Return>", lambda e: self._apply_chapter_id_title())

        ttk.Label(edit_tab, text=tr("chapter_title")).grid(row=1, column=0, sticky="w")
        self.ent_ch_title = tk.Text(edit_tab, height=1, wrap="none")
        self.ent_ch_title.grid(row=1, column=1, sticky="ew", pady=(0, 6))
        self.ent_ch_title.bind("<FocusOut>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_title.bind("<Return>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_title.bind("<KeyRelease>", lambda e: highlight_variables(self.ent_ch_title))
        self.auto_ch_title = VarAutocomplete(self.ent_ch_title, lambda: self._collect_variables())
        highlight_variables(self.ent_ch_title)
        ttk.Button(edit_tab, text="$", width=2, command=self.auto_ch_title.trigger).grid(row=1, column=2, padx=(4, 0))

        ttk.Label(edit_tab, text=tr("branch_id")).grid(row=2, column=0, sticky="w")
        self.ent_br_id = ttk.Entry(edit_tab)
        self.ent_br_id.grid(row=2, column=1, sticky="ew", pady=(0, 6))
        self.ent_br_id.bind("<FocusOut>", lambda e: self._apply_branch_id_title())
        self.ent_br_id.bind("<Return>", lambda e: self._apply_branch_id_title())

        ttk.Label(edit_tab, text=tr("branch_title")).grid(row=3, column=0, sticky="w")
        self.ent_br_title = tk.Text(edit_tab, height=1, wrap="none")
        self.ent_br_title.grid(row=3, column=1, sticky="ew", pady=(0, 6))
        self.ent_br_title.bind("<FocusOut>", lambda e: self._apply_branch_id_title())
        self.ent_br_title.bind("<Return>", lambda e: self._apply_branch_id_title())
        self.ent_br_title.bind("<KeyRelease>", lambda e: highlight_variables(self.ent_br_title))
        self.auto_br_title = VarAutocomplete(self.ent_br_title, lambda: self._collect_variables())
        highlight_variables(self.ent_br_title)
        ttk.Button(edit_tab, text="$", width=2, command=self.auto_br_title.trigger).grid(row=3, column=2, padx=(4, 0))

        # 본문
        body_frame = ttk.LabelFrame(edit_tab, text=tr("body_label"), padding=6)
        body_frame.grid(row=4, column=0, columnspan=3, sticky="nsew")
        body_frame.rowconfigure(0, weight=1)
        body_frame.columnconfigure(0, weight=1)

        self.txt_body = tk.Text(body_frame, wrap="word", undo=True, height=20,
                                font=("Malgun Gothic", 12) if sys.platform.startswith("win") else ("Noto Sans CJK KR",
                                                                                                   12))
        self.txt_body.grid(row=0, column=0, sticky="nsew")
        scr = ttk.Scrollbar(body_frame, orient="vertical", command=self.txt_body.yview)
        scr.grid(row=0, column=1, sticky="ns")
        self.txt_body.configure(yscrollcommand=scr.set)
        self.auto_body = VarAutocomplete(self.txt_body, lambda: self._collect_variables())
        self.txt_body.bind("<KeyRelease>", lambda e: highlight_variables(self.txt_body))
        highlight_variables(self.txt_body)
        ttk.Button(body_frame, text="$", width=2, command=self.auto_body.trigger).grid(row=0, column=2, padx=(4, 0), sticky="ns")
        self.txt_body.bind("<<Modified>>", self._on_body_modified)

        # 선택지 편집
        choices_frame = ttk.LabelFrame(edit_tab, text=tr("choices_section"), padding=6)
        choices_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        choices_frame.columnconfigure(0, weight=1)

        self.tree_choices = ttk.Treeview(choices_frame, columns=("text", "target"), show="headings", height=6)
        self.tree_choices.heading("text", text=tr("button_text"))
        self.tree_choices.heading("target", text=tr("target_branch_id"))
        self.tree_choices.column("text", width=400, anchor="w")
        self.tree_choices.column("target", width=160, anchor="w")
        self.tree_choices.grid(row=0, column=0, sticky="ew")

        ch_btns = ttk.Frame(choices_frame)
        ch_btns.grid(row=0, column=1, sticky="ns")
        ttk.Button(ch_btns, text=tr("add"), command=self._add_choice).grid(row=0, column=0, pady=(0, 4))
        ttk.Button(ch_btns, text=tr("edit"), command=self._edit_choice).grid(row=1, column=0, pady=4)
        ttk.Button(ch_btns, text=tr("delete"), command=self._delete_choice).grid(row=2, column=0, pady=4)
        ttk.Button(ch_btns, text=tr("up"), command=lambda: self._reorder_choice(-1)).grid(row=3, column=0, pady=4)
        ttk.Button(ch_btns, text=tr("down"), command=lambda: self._reorder_choice(1)).grid(row=4, column=0, pady=4)

        # 미리보기 탭
        preview_tab = ttk.Frame(right, padding=8)
        right.add(preview_tab, text=tr("preview_tab"))
        preview_tab.rowconfigure(0, weight=1)
        preview_tab.columnconfigure(0, weight=1)

        self.txt_preview = tk.Text(
            preview_tab,
            wrap="none",
            font=("Consolas", 11) if sys.platform.startswith("win") else ("Menlo", 11),
            undo=True,
        )
        self.txt_preview.grid(row=0, column=0, sticky="nsew")
        pvx = ttk.Scrollbar(preview_tab, orient="horizontal", command=self.txt_preview.xview)
        pvy = ttk.Scrollbar(preview_tab, orient="vertical", command=self.txt_preview.yview)
        pvx.grid(row=1, column=0, sticky="ew")
        pvy.grid(row=0, column=1, sticky="ns")
        self.txt_preview.configure(xscrollcommand=pvx.set, yscrollcommand=pvy.set)
        self.txt_preview.bind("<<Modified>>", self._on_preview_modified)
        self.txt_preview.bind("<FocusOut>", self._on_preview_focus_out)
        self.txt_preview.edit_modified(False)

        # 찾기/변경은 새 창에서 열림
        self.find_win = None

        # 하단 버튼 바
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        # 왼쪽: 분석/검사
        left_btns = ttk.Frame(bottom)
        left_btns.pack(side="left")
        ttk.Button(left_btns, text=tr("validate_story"), command=self._validate_story).pack(side="left")
        ttk.Button(left_btns, text=tr("analyze_loops"), command=self._analyze_infinite_loops).pack(side="left", padx=(6, 0))
        # 오른쪽: 저장/미리보기
        right_btns = ttk.Frame(bottom)
        right_btns.pack(side="right")
        ttk.Button(right_btns, text=tr("save"), command=self._save_file).pack(side="right")
        ttk.Button(right_btns, text=tr("apply_preview_btn"), command=self._apply_preview_to_model).pack(side="right", padx=(0, 6))
        ttk.Button(right_btns, text=tr("refresh_preview_btn"), command=self._update_preview).pack(side="right", padx=(0, 6))
        ttk.Button(right_btns, text=tr("run_preview_btn"), command=self._run_preview).pack(side="right", padx=(0, 6))

        root.pack(fill="both", expand=True)

    # ---------- 핸들러 ----------
    def _on_title_changed(self):
        self.story.title = self.ent_title.get("1.0", "end-1c").strip() or "Untitled"
        self._set_dirty(True)
        self._update_preview()

    def _on_start_changed(self):
        sid = self.cmb_start.get().strip()
        if sid:
            self.story.start_id = sid
            self._set_dirty(True)
            self._update_preview()

    def _on_ending_changed(self):
        self.story.ending_text = self.ent_end.get().strip() or "The End"
        self._set_dirty(True)
        self._update_preview()

    def _on_show_disabled_changed(self):
        self.story.show_disabled = self.var_show_disabled.get()
        self._set_dirty(True)
        self._update_preview()

    def _on_select_chapter(self):
        sel = self.lst_chapters.curselection()
        if not sel:
            return
        idx = sel[0]
        cid = list(self.story.chapters.keys())[idx]
        if self.current_chapter_id != cid:
            self._apply_body_to_model()
            self._load_chapter_to_form(cid)

    def _on_select_branch(self):
        sel = self.lst_branches.curselection()
        if not sel or self.current_chapter_id is None:
            return
        idx = sel[0]
        ch = self.story.chapters[self.current_chapter_id]
        bid = list(ch.branches.keys())[idx]
        if self.current_branch_id != bid:
            self._apply_body_to_model()
            self._load_branch_to_form(bid)

    def _on_body_modified(self, evt):
        # Text의 Modified 플래그를 수동 리셋
        if self.txt_body.edit_modified():
            self.txt_body.edit_modified(False)
            self._set_dirty(True)
            self._apply_body_to_model()
            self._update_preview()

    def _on_preview_modified(self, evt):
        if self.txt_preview.edit_modified():
            self.txt_preview.edit_modified(False)
            if not self._preview_updating:
                self.preview_modified = True
                self._set_dirty(True)

    def _on_preview_focus_out(self, evt):
        if not self._ensure_preview_applied():
            self.after(0, lambda: self.txt_preview.focus_set())

    def _ensure_preview_applied(self) -> bool:
        # 미리보기에 수정본이 없으면 그대로 진행
        if not self.preview_modified:
            return True

        res = messagebox.askyesnocancel(
            tr("preview_apply"),
            tr("preview_apply_prompt"),
            parent=self,
        )
        if res is None:
            # 취소
            return False
        if res:
            # 예: 미리보기 텍스트 → 모델 반영(파싱 실패 시 False)
            if not self._apply_preview_to_model():
                return False
            return True
        else:
            # 아니오: 미리보기 변경을 버리고 모델 기준으로 강제 갱신
            self.preview_modified = False
            self._update_preview(force=True)
            return True

    # ---------- 상호작용 ----------
    def _load_chapter_to_form(self, cid: str):
        self.current_chapter_id = cid
        ch = self.story.chapters[cid]
        self.ent_ch_id.delete(0, tk.END)
        self.ent_ch_id.insert(0, ch.chapter_id)
        self.ent_ch_title.delete("1.0", tk.END)
        self.ent_ch_title.insert("1.0", ch.title)
        highlight_variables(self.ent_ch_title)
        self._refresh_branch_list()
        first = next(iter(ch.branches.keys()), None)
        if first:
            self._load_branch_to_form(first)

    def _load_branch_to_form(self, bid: str):
        self.current_branch_id = bid
        br = self.story.branches[bid]
        self.ent_br_id.delete(0, tk.END)
        self.ent_br_id.insert(0, br.branch_id)
        self.ent_br_title.delete("1.0", tk.END)
        self.ent_br_title.insert("1.0", br.title)
        highlight_variables(self.ent_br_title)

        self.txt_body.config(state="normal")
        self.txt_body.delete("1.0", tk.END)
        if br.paragraphs:
            self.txt_body.insert(tk.END, "\n\n".join(br.paragraphs))
        highlight_variables(self.txt_body)
        self.txt_body.edit_modified(False)

        for i in self.tree_choices.get_children():
            self.tree_choices.delete(i)
        for c in br.choices:
            self.tree_choices.insert("", tk.END, values=(c.text, c.target_id))

        self._refresh_meta_panel()
        self._update_preview()

    def _apply_body_to_model(self):
        if self.current_branch_id is None:
            return
        br = self.story.branches[self.current_branch_id]
        raw = self.txt_body.get("1.0", tk.END).rstrip("\n")
        paras = [p.strip() for p in raw.split("\n\n")]
        paras = [p for p in paras if p != ""]
        br.paragraphs = paras

    def _apply_chapter_id_title(self):
        if self.current_chapter_id is None:
            return
        new_id = self.ent_ch_id.get().strip()
        new_title = self.ent_ch_title.get("1.0", "end-1c").strip()
        if not new_id:
            messagebox.showerror(tr("error"), tr("chapter_id_required"))
            self.ent_ch_id.focus_set()
            return
        cur_id = self.current_chapter_id
        if new_id != cur_id:
            if new_id in self.story.chapters:
                messagebox.showerror(tr("error"), tr("chapter_id_exists", id=new_id))
                self.ent_ch_id.delete(0, tk.END)
                self.ent_ch_id.insert(0, cur_id)
                return
            ch_obj = self.story.chapters.pop(cur_id)
            ch_obj.chapter_id = new_id
            self.story.chapters[new_id] = ch_obj
            for br in ch_obj.branches.values():
                br.chapter_id = new_id
            self.current_chapter_id = new_id
        self.story.chapters[new_id].title = new_title
        self._refresh_chapter_list()
        self._set_dirty(True)
        self._update_preview()

    def _apply_branch_id_title(self):
        if self.current_branch_id is None:
            return
        new_id = self.ent_br_id.get().strip()
        new_title = self.ent_br_title.get("1.0", "end-1c").strip()
        if not new_id:
            messagebox.showerror(tr("error"), tr("branch_id_required"))
            self.ent_br_id.focus_set()
            return
        cur_id = self.current_branch_id
        if new_id != cur_id:
            if new_id in self.story.branches:
                messagebox.showerror(tr("error"), tr("branch_id_exists", id=new_id))
                self.ent_br_id.delete(0, tk.END)
                self.ent_br_id.insert(0, cur_id)
                return
            br_obj = self.story.branches.pop(cur_id)
            br_obj.branch_id = new_id
            self.story.branches[new_id] = br_obj
            ch = self.story.chapters[br_obj.chapter_id]
            ch.branches.pop(cur_id)
            ch.branches[new_id] = br_obj
            for other in self.story.branches.values():
                for c in other.choices:
                    if c.target_id == cur_id:
                        c.target_id = new_id
            if self.story.start_id == cur_id:
                self.story.start_id = new_id
            self.current_branch_id = new_id
        self.story.branches[new_id].title = new_title
        self._refresh_branch_list()
        self._refresh_meta_panel()
        self._set_dirty(True)
        self._update_preview()

    def _refresh_chapter_list(self):
        self.lst_chapters.delete(0, tk.END)
        for cid, ch in self.story.chapters.items():
            self.lst_chapters.insert(tk.END, f"{cid}  |  {ch.title}")
        if self.current_chapter_id and self.current_chapter_id in self.story.chapters:
            idx = list(self.story.chapters.keys()).index(self.current_chapter_id)
            self.lst_chapters.selection_clear(0, tk.END)
            self.lst_chapters.selection_set(idx)
            self.lst_chapters.see(idx)
        self._refresh_branch_list()
        self._refresh_meta_panel()

    def _refresh_branch_list(self):
        self.lst_branches.delete(0, tk.END)
        if self.current_chapter_id is None:
            return
        ch = self.story.chapters[self.current_chapter_id]
        for bid, br in ch.branches.items():
            self.lst_branches.insert(tk.END, f"{bid}  |  {br.title}")
        if self.current_branch_id and self.current_branch_id in ch.branches:
            idx = list(ch.branches.keys()).index(self.current_branch_id)
            self.lst_branches.selection_clear(0, tk.END)
            self.lst_branches.selection_set(idx)
            self.lst_branches.see(idx)

    def _refresh_meta_panel(self):
        ids = list(self.story.branches.keys())
        self.cmb_start["values"] = ids
        if self.story.start_id in ids:
            self.cmb_start.set(self.story.start_id)
        elif ids:
            self.cmb_start.set(ids[0])
            self.story.start_id = ids[0]
        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, self.story.ending_text)
        self.var_show_disabled.set(self.story.show_disabled)
        self._refresh_variable_list()

    def _add_chapter(self):
        # 현재 변경사항 반영
        self._apply_body_to_model()
        new_cid = self.story.ensure_unique_chapter_id("chapter")
        chapter = Chapter(chapter_id=new_cid, title="New Chapter")
        self.story.chapters[new_cid] = chapter
        new_bid = self.story.ensure_unique_branch_id("branch")
        branch = Branch(branch_id=new_bid, title="New Branch", chapter_id=new_cid)
        chapter.branches[new_bid] = branch
        self.story.branches[new_bid] = branch
        self.current_chapter_id = new_cid
        self.current_branch_id = new_bid
        self._refresh_chapter_list()
        self._load_chapter_to_form(new_cid)
        self._set_dirty(True)

    def _delete_current_chapter(self):
        if self.current_chapter_id is None:
            return
        if len(self.story.chapters) <= 1:
            messagebox.showwarning(tr("warning"), tr("at_least_one_chapter"))
            return
        cid = self.current_chapter_id
        ch = self.story.chapters[cid]
        if messagebox.askyesno(tr("confirm_delete"), tr("delete_chapter_prompt", id=cid)):
            for bid in list(ch.branches.keys()):
                self.story.branches.pop(bid, None)
                if self.story.start_id == bid:
                    self.story.start_id = None
            self.story.chapters.pop(cid)
            keys = list(self.story.chapters.keys())
            next_cid = keys[0] if keys else None
            self.current_chapter_id = next_cid
            if next_cid:
                next_bid = next(iter(self.story.chapters[next_cid].branches.keys()), None)
                self.current_branch_id = next_bid
            else:
                self.current_branch_id = None
            if self.story.start_id is None and self.current_branch_id:
                self.story.start_id = self.current_branch_id
            self._refresh_chapter_list()
            if self.current_chapter_id and self.current_branch_id:
                self._load_chapter_to_form(self.current_chapter_id)
            self._set_dirty(True)

    def _reorder_chapter(self, delta: int):
        if self.current_chapter_id is None:
            return
        keys = list(self.story.chapters.keys())
        idx = keys.index(self.current_chapter_id)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(keys):
            return
        # dict 재구성으로 순서 변경
        reordered = {}
        keys[idx], keys[new_idx] = keys[new_idx], keys[idx]
        for k in keys:
            reordered[k] = self.story.chapters[k]
        self.story.chapters = reordered
        self._refresh_chapter_list()
        self._set_dirty(True)

    def _add_branch(self):
        if self.current_chapter_id is None:
            return
        self._apply_body_to_model()
        new_id = self.story.ensure_unique_branch_id("branch")
        br = Branch(branch_id=new_id, title="New Branch", chapter_id=self.current_chapter_id)
        self.story.branches[new_id] = br
        self.story.chapters[self.current_chapter_id].branches[new_id] = br
        self.current_branch_id = new_id
        self._refresh_branch_list()
        self._load_branch_to_form(new_id)
        self._set_dirty(True)

    def _delete_current_branch(self):
        if self.current_branch_id is None or self.current_chapter_id is None:
            return
        ch = self.story.chapters[self.current_chapter_id]
        if len(ch.branches) <= 1:
            messagebox.showwarning(tr("warning"), tr("at_least_one_branch"))
            return
        bid = self.current_branch_id
        if messagebox.askyesno(tr("confirm_delete"), tr("delete_branch_prompt", id=bid)):
            ch.branches.pop(bid, None)
            self.story.branches.pop(bid, None)
            if self.story.start_id == bid:
                self.story.start_id = next(iter(self.story.branches.keys()), None)
            next_bid = next(iter(ch.branches.keys()))
            self.current_branch_id = next_bid
            self._refresh_branch_list()
            self._load_branch_to_form(next_bid)
            self._set_dirty(True)

    def _reorder_branch(self, delta: int):
        if self.current_branch_id is None or self.current_chapter_id is None:
            return
        ch = self.story.chapters[self.current_chapter_id]
        keys = list(ch.branches.keys())
        idx = keys.index(self.current_branch_id)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(keys):
            return
        reordered = {}
        keys[idx], keys[new_idx] = keys[new_idx], keys[idx]
        for k in keys:
            reordered[k] = ch.branches[k]
        ch.branches = reordered
        self._refresh_branch_list()
        self._set_dirty(True)

    def _collect_variables(self) -> List[str]:
        vars_set = set(self.story.variables.keys())
        for br in self.story.branches.values():
            for act in br.actions:
                vars_set.add(act.var)
        return sorted(vars_set)

    def _refresh_variable_list(self):
        for i in self.tree_vars.get_children():
            self.tree_vars.delete(i)
        for name, val in self.story.variables.items():
            val_str = str(val).lower() if isinstance(val, bool) else val
            self.tree_vars.insert("", tk.END, values=(name, val_str))

    def _add_variable(self):
        dlg = VariableDialog(self)
        if dlg.result_ok:
            if dlg.var_name in self.story.variables:
                messagebox.showerror(tr("error"), tr("variable_name_exists"))
                return
            self.story.variables[dlg.var_name] = dlg.value
            self._refresh_variable_list()
            self._set_dirty(True)
            self._update_preview()

    def _edit_variable(self):
        sel = self.tree_vars.selection()
        if not sel:
            return
        name = self.tree_vars.item(sel[0], "values")[0]
        cur_val = self.story.variables.get(name)
        dlg = VariableDialog(self, name, cur_val)
        if dlg.result_ok:
            if dlg.var_name != name and dlg.var_name in self.story.variables:
                messagebox.showerror(tr("error"), tr("variable_name_exists"))
                return
            if dlg.var_name != name:
                self.story.variables.pop(name, None)
            self.story.variables[dlg.var_name] = dlg.value
            self._refresh_variable_list()
            self._set_dirty(True)
            self._update_preview()

    def _delete_variable(self):
        sel = self.tree_vars.selection()
        if not sel:
            return
        name = self.tree_vars.item(sel[0], "values")[0]
        if messagebox.askyesno(tr("confirm_delete"), tr("delete_variable_prompt", name=name)):
            self.story.variables.pop(name, None)
            self._refresh_variable_list()
            self._set_dirty(True)
            self._update_preview()

    def _add_choice(self):
        if self.current_branch_id is None:
            return
        ids = list(self.story.branches.keys())
        vars = self._collect_variables()
        dlg = ChoiceEditor(self, tr("add_choice"), None, ids, vars)
        if dlg.result_ok and dlg.choice:
            br = self.story.branches[self.current_branch_id]
            br.choices.append(dlg.choice)
            self.tree_choices.insert("", tk.END, values=(dlg.choice.text, dlg.choice.target_id))
            self._set_dirty(True)
            self._update_preview()

    def _edit_choice(self):
        sel = self.tree_choices.selection()
        if not sel or self.current_branch_id is None:
            return
        idx = self.tree_choices.index(sel[0])
        br = self.story.branches[self.current_branch_id]
        cur = br.choices[idx]
        ids = list(self.story.branches.keys())
        vars = self._collect_variables()
        dlg = ChoiceEditor(self, tr("edit_choice"), cur, ids, vars)
        if dlg.result_ok and dlg.choice:
            br.choices[idx] = dlg.choice
            self.tree_choices.item(sel[0], values=(dlg.choice.text, dlg.choice.target_id))
            self._set_dirty(True)
            self._update_preview()

    def _delete_choice(self):
        sel = self.tree_choices.selection()
        if not sel or self.current_branch_id is None:
            return
        idx = self.tree_choices.index(sel[0])
        br = self.story.branches[self.current_branch_id]
        br.choices.pop(idx)
        self.tree_choices.delete(sel[0])
        self._set_dirty(True)
        self._update_preview()

    def _reorder_choice(self, delta: int):
        sel = self.tree_choices.selection()
        if not sel or self.current_branch_id is None:
            return
        cur_idx = self.tree_choices.index(sel[0])
        new_idx = cur_idx + delta
        br = self.story.branches[self.current_branch_id]
        if new_idx < 0 or new_idx >= len(br.choices):
            return
        br.choices[cur_idx], br.choices[new_idx] = br.choices[new_idx], br.choices[cur_idx]
        for i in self.tree_choices.get_children():
            self.tree_choices.delete(i)
        for c in br.choices:
            self.tree_choices.insert("", tk.END, values=(c.text, c.target_id))
        self.tree_choices.selection_set(self.tree_choices.get_children()[new_idx])
        self._set_dirty(True)
        self._update_preview()

    # ---------- 찾기/변경 ----------
    def _open_find_window(self):
        if self.find_win is not None and self.find_win.winfo_exists():
            self.find_win.deiconify()
            self.find_win.lift()
            self.ent_find.focus_set()
            return
        win = tk.Toplevel(self)
        win.title(tr("find_replace"))
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._close_find_window)
        self.find_win = win

        win.columnconfigure(1, weight=1)

        scope_frame = ttk.LabelFrame(win, text=tr("search_scope"), padding=6)
        scope_frame.grid(row=0, column=0, columnspan=2, sticky="w")
        self.find_scope = tk.StringVar(value="branch")
        ttk.Radiobutton(scope_frame, text=tr("this_branch"), variable=self.find_scope, value="branch").pack(side="left")
        ttk.Radiobutton(scope_frame, text=tr("entire_project"), variable=self.find_scope, value="project").pack(side="left", padx=10)

        ttk.Label(win, text=tr("find_string")).grid(row=1, column=0, sticky="w", pady=(10,0))
        self.ent_find = ttk.Entry(win)
        self.ent_find.grid(row=1, column=1, sticky="ew", pady=(10,0))

        ttk.Label(win, text=tr("replace_string")).grid(row=2, column=0, sticky="w", pady=(6,0))
        self.ent_replace = ttk.Entry(win)
        self.ent_replace.grid(row=2, column=1, sticky="ew", pady=(6,0))

        nav = ttk.Frame(win)
        nav.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(nav, text=tr("previous"), command=lambda: self._find_step(-1)).pack(side="left")
        ttk.Button(nav, text=tr("next"), command=lambda: self._find_step(1)).pack(side="left", padx=5)
        ttk.Button(nav, text=tr("replace"), command=self._replace_current).pack(side="left", padx=5)

        self.ent_find.focus_set()

    def _close_find_window(self):
        if self.find_win is not None:
            self.find_win.destroy()
            self.find_win = None
        self.ent_find = None
        self.ent_replace = None
        self.find_scope = None
        self.txt_body.tag_remove("find_highlight", "1.0", tk.END)
        self.find_results = []
        self.find_index = -1

    def _build_find_results(self, query: str, scope: str):
        self._apply_body_to_model()
        results: List[Tuple[str, int]] = []
        if scope == "branch" and self.current_branch_id:
            br = self.story.branches[self.current_branch_id]
            text = "\n\n".join(br.paragraphs)
            idx = text.find(query)
            while idx != -1:
                results.append((self.current_branch_id, idx))
                idx = text.find(query, idx + len(query))
        else:
            for bid, br in self.story.branches.items():
                text = "\n\n".join(br.paragraphs)
                idx = text.find(query)
                while idx != -1:
                    results.append((bid, idx))
                    idx = text.find(query, idx + len(query))
        self.find_results = results
        self.find_index = -1
        self._last_find_text = query
        self._last_find_scope = scope

    def _find_step(self, delta: int):
        query = self.ent_find.get()
        if not query:
            return
        scope = self.find_scope.get()
        if (query != self._last_find_text or scope != self._last_find_scope or
                not self.find_results):
            self._build_find_results(query, scope)
        if not self.find_results:
            messagebox.showinfo(tr("find_title"), tr("find_no_results"))
            return
        self.find_index = (self.find_index + delta) % len(self.find_results)
        bid, pos = self.find_results[self.find_index]
        br = self.story.get_branch(bid)
        if br and br.chapter_id != self.current_chapter_id:
            self._load_chapter_to_form(br.chapter_id)
        if bid != self.current_branch_id:
            self._load_branch_to_form(bid)
        self.txt_body.tag_remove("find_highlight", "1.0", tk.END)
        start = f"1.0+{pos}c"
        end = f"{start}+{len(query)}c"
        self.txt_body.tag_add("find_highlight", start, end)
        self.txt_body.tag_config("find_highlight", background="yellow", foreground="black")
        self.txt_body.tag_remove(tk.SEL, "1.0", tk.END)
        self.txt_body.tag_add(tk.SEL, start, end)
        self.txt_body.mark_set(tk.INSERT, end)
        self.txt_body.see(start)
        self.txt_body.focus_set()

    def _replace_current(self):
        query = self.ent_find.get()
        if not query:
            return
        replacement = self.ent_replace.get()
        if self.find_index < 0 or not self.find_results:
            self._find_step(1)
            if self.find_index < 0 or not self.find_results:
                return
        bid, pos = self.find_results[self.find_index]
        br = self.story.get_branch(bid)
        if br and br.chapter_id != self.current_chapter_id:
            self._load_chapter_to_form(br.chapter_id)
        if bid != self.current_branch_id:
            self._load_branch_to_form(bid)
        start = f"1.0+{pos}c"
        end = f"{start}+{len(query)}c"
        self.txt_body.delete(start, end)
        self.txt_body.insert(start, replacement)
        highlight_variables(self.txt_body)
        self._apply_body_to_model()
        self._build_find_results(query, self.find_scope.get())
        self._find_step(1)

    def _update_preview(self, force: bool = False):
        # 사용자가 미리보기를 수정했을 때는 기본 덮어쓰기를 막는다.
        # 단, 의도적으로 버리기/강제 동기화가 필요할 땐 force=True로 호출.
        if self.preview_modified and not force:
            return

        self._apply_body_to_model()
        txt = self.story.serialize()

        self._preview_updating = True
        try:
            self.txt_preview.delete("1.0", tk.END)
            self.txt_preview.insert(tk.END, txt)
            self.txt_preview.edit_modified(False)
        finally:
            self._preview_updating = False

        self.preview_modified = False

    def _apply_preview_to_model(self) -> bool:
        if not self.preview_modified:
            return True
        txt = self.txt_preview.get("1.0", tk.END)
        parser = StoryParser()
        try:
            story = parser.parse(txt)
        except ParseError as e:
            messagebox.showerror(tr("parse_error"), str(e))
            return False
        self.story = story
        self.current_branch_id = story.start_id
        br = self.story.get_branch(self.current_branch_id) if self.current_branch_id else None
        self.current_chapter_id = (
            br.chapter_id if br else (next(iter(self.story.chapters.keys())) if self.story.chapters else None)
        )
        self.ent_title.delete("1.0", tk.END)
        self.ent_title.insert("1.0", self.story.title)
        highlight_variables(self.ent_title)
        self._refresh_chapter_list()
        # 미리보기에서 변경된 메타데이터를 반영
        self._refresh_meta_panel()
        if self.current_chapter_id:
            self._load_chapter_to_form(self.current_chapter_id)
            if self.current_branch_id:
                self._load_branch_to_form(self.current_branch_id)
        else:
            self.txt_body.delete("1.0", tk.END)
            highlight_variables(self.txt_body)
            for i in self.tree_choices.get_children():
                self.tree_choices.delete(i)
        # 미리보기 텍스트의 수정 플래그 초기화
        self.txt_preview.edit_modified(False)
        self.preview_modified = False
        return True

    def _run_preview(self):
        """branching_novel.py에 의존하지 않고 내장 실행기로 현재 스토리를 실행한다."""
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()

        import copy

        preview_story = copy.deepcopy(self.story)
        file_path = self.current_file or "<preview>"
        app = BranchingNovelApp(preview_story, file_path, show_disabled=self.story.show_disabled)
        app.mainloop()

    def _validate_story(self):
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()
        errors = []
        warnings = []

        if not self.story.title.strip():
            errors.append(tr("story_title_empty"))
        if not self.story.start_id or self.story.start_id not in self.story.branches:
            errors.append(tr("invalid_start"))

        ids = set(self.story.branches.keys())
        for bid, br in self.story.branches.items():
            if not br.branch_id.strip():
                errors.append(tr("branch_id_empty", id=bid))
            if br.branch_id != bid:
                errors.append(tr("branch_id_mismatch", id=bid, branch_id=br.branch_id))
            for c in br.choices:
                if c.target_id not in ids:
                    warnings.append(tr("warn_choice_target_missing", id=bid, text=c.text, target=c.target_id))

        for cid, ch in self.story.chapters.items():
            if not ch.branches:
                warnings.append(tr("warn_chapter_no_branches", id=cid))

        msg = []
        if errors:
            msg.append(tr("errors_label"))
            msg.extend(f"- {e}" for e in errors)
        if warnings:
            if msg:
                msg.append("")
            msg.append(tr("warnings_label"))
            msg.extend(f"- {w}" for w in warnings)

        if not msg:
            messagebox.showinfo(tr("validation_title"), tr("validation_ok"))
        else:
            messagebox.showwarning(tr("validation_result_title"), "\n".join(msg))

    # ---------- 파일 입출력 ----------
    def _new_story(self):
        if not self._confirm_discard_changes():
            return
        self.story = Story()
        ch_id = self.story.ensure_unique_chapter_id("chapter")
        chapter = Chapter(chapter_id=ch_id, title="Introduction")
        self.story.chapters[ch_id] = chapter
        br_id = self.story.ensure_unique_branch_id("intro")
        branch = Branch(branch_id=br_id, title="Introduction", chapter_id=ch_id)
        chapter.branches[br_id] = branch
        self.story.branches[br_id] = branch
        self.story.start_id = br_id
        self.current_chapter_id = ch_id
        self.current_branch_id = br_id
        self.current_file = None
        self.ent_title.delete("1.0", tk.END)
        self.ent_title.insert("1.0", self.story.title)
        highlight_variables(self.ent_title)
        self._refresh_chapter_list()
        self._load_chapter_to_form(ch_id)
        self._refresh_meta_panel()
        self._update_preview()
        self._set_dirty(False)

    def _open_file(self):
        if not self._confirm_discard_changes():
            return
        path = filedialog.askopenfilename(title=tr("open_title"), filetypes=[("Branching Novel Files","*.bnov"),("All Files","*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            parser = StoryParser()
            story = parser.parse(text)
        except ParseError as e:
            messagebox.showerror(tr("parse_error"), str(e))
            return
        except Exception as e:
            messagebox.showerror(tr("error"), tr("open_file_error", err=e))
            return

        self.story = story
        self.current_branch_id = story.start_id
        br = self.story.get_branch(self.current_branch_id) if self.current_branch_id else None
        self.current_chapter_id = br.chapter_id if br else (next(iter(self.story.chapters.keys())) if self.story.chapters else None)
        self.current_file = path

        self.ent_title.delete("1.0", tk.END)
        self.ent_title.insert("1.0", self.story.title)
        highlight_variables(self.ent_title)
        self._refresh_chapter_list()
        if self.current_chapter_id:
            self._load_chapter_to_form(self.current_chapter_id)
            if self.current_branch_id:
                self._load_branch_to_form(self.current_branch_id)
        self._refresh_meta_panel()
        self._update_preview()
        self._set_dirty(False)
        self.title(f"Branching Novel Editor - {os.path.basename(path)}")

    def _save_file(self):
        if self.current_file is None:
            self._save_file_as()
            return
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()
        txt = self.story.serialize()
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(txt + "\n")
        except Exception as e:
            messagebox.showerror(tr("error"), tr("save_error", err=e))
            return
        self._set_dirty(False)
        messagebox.showinfo(tr("save_title"), tr("save_done"))

    def _save_file_as(self):
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()
        path = filedialog.asksaveasfilename(
            title=tr("save_as_title"),
            defaultextension=".bnov",
            filetypes=[("Branching Novel Files","*.bnov"),("All Files","*.*")],
            initialfile="story.bnov"
        )
        if not path:
            return
        txt = self.story.serialize()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt + "\n")
        except Exception as e:
            messagebox.showerror(tr("error"), tr("save_error", err=e))
            return
        self.current_file = path
        self._set_dirty(False)
        self.title(f"Branching Novel Editor - {os.path.basename(path)}")
        messagebox.showinfo(tr("save_title"), tr("save_done"))

    def _exit_app(self):
        # 1) 미리보기에서 수정한 내용이 있으면 먼저 처리(반영 or 폐기)
        if not self._ensure_preview_applied():
            return

        # 2) 더티 플래그가 있으면 저장 여부 확인
        if self.dirty:
            res = messagebox.askyesnocancel(tr("unsaved_changes_title"), tr("unsaved_changes_prompt"))
            if res is None:
                # 취소
                return
            if res is True:
                # 예: 저장 시도
                self._save_file()
                # 저장이 성공하면 self.dirty가 False가 됨(저장 취소/실패 시 여전히 True)
                if self.dirty:
                    # 사용자가 '다른 이름으로 저장'에서 취소했거나, 파싱/저장 오류로 실패
                    return
                # 저장 성공 → 종료
                self.destroy()
                return
            # res is False (아니오) → 저장하지 않고 종료
            self.destroy()
            return

        # 3) 변경사항이 없으면 바로 종료
        self.destroy()

    def _confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        res = messagebox.askyesnocancel(tr("unsaved_changes_title"), tr("unsaved_changes_prompt"))
        if res is None:
            return False
        if res is True:
            self._save_file()
            return not self.dirty
        return True

    def _set_dirty(self, val: bool):
        self.dirty = val
        mark = "*" if self.dirty else ""
        base = "Branching Novel Editor"
        tail = f" - {os.path.basename(self.current_file)}" if self.current_file else ""
        self.title(f"{base}{tail}{mark}")

    # ---------- 무한 루프 검사 ----------
    def _analyze_infinite_loops(self):
        """
        무한 루프 간단 리포트:
        - 강한 해석(가드 기반 고정점 + SCC + 경로 시뮬레이션)은 유지
        - 출력은 요약/조치 중심으로 간결화
        """
        import math
        import tkinter as tk
        from tkinter import ttk, messagebox

        # 1) 모델 최신화
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()

        story = self.story
        branches = story.branches
        start_id = story.start_id

        if not start_id or start_id not in branches:
            messagebox.showerror(tr("error"), tr("invalid_start"))
            return

        # -----------------------
        # 공용 유틸
        # -----------------------
        EPS = 1e-9
        BIG = 1e18

        def as_point(v):
            if isinstance(v, bool):
                v = int(v)
            return (float(v), float(v))

        def join_interval(a, b):
            alo, ahi = a
            blo, bhi = b
            return (min(alo, blo), max(ahi, bhi))

        def meet_interval(iv, lower=None, upper=None, open_lower=False, open_upper=False):
            lo, hi = iv
            if lower is not None:
                lo = max(lo, lower + (EPS if open_lower else 0.0))
            if upper is not None:
                hi = min(hi, upper - (EPS if open_upper else 0.0))
            if lo > hi:
                return None
            return (lo, hi)

        def widen_unknown(_iv):
            return (-BIG, BIG)

        # 조건 파싱/평가(AND만 지원)
        simple_atom_re = re.compile(r"^\s*([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<)\s*([^\s]+)\s*$", re.IGNORECASE)

        def _num_parse(val_text):
            vv = val_text.strip().lower()
            if vv == "true":  return 1.0
            if vv == "false": return 0.0
            if re.match(r"^-?\d+$", vv): return float(int(vv))
            try:
                return float(vv)
            except Exception:
                return None

        def parse_condition(cond_text):
            if not cond_text or cond_text.strip() == "": return []
            lc = cond_text.lower()
            if " or " in lc or " not " in lc or "(" in lc or ")" in lc or "|" in cond_text or "&" in cond_text:
                return None  # 복잡식은 불확실
            parts = re.split(r"\s+and\s+", cond_text, flags=re.IGNORECASE)
            atoms = []
            for part in parts:
                m = simple_atom_re.match(part)
                if not m: return None
                var, op, val = m.groups()
                c = _num_parse(val)
                if c is None: return None
                atoms.append((var, op, c))
            return atoms

        def eval_atoms_over_interval(atoms, state_map):
            # 항상 참/항상 거짓/불확실(None)
            result = True
            for var, op, c in atoms:
                lo, hi = state_map.get(var, as_point(0.0))
                tri = None
                if op == "==":
                    if lo == hi == c:
                        tri = True
                    elif c < lo or c > hi:
                        tri = False
                elif op == "!=":
                    if lo == hi == c:
                        tri = False
                    elif c < lo or c > hi:
                        tri = True
                elif op == ">":
                    if lo > c:
                        tri = True
                    elif hi <= c:
                        tri = False
                elif op == ">=":
                    if lo >= c:
                        tri = True
                    elif hi < c:
                        tri = False
                elif op == "<":
                    if hi < c:
                        tri = True
                    elif lo >= c:
                        tri = False
                elif op == "<=":
                    if hi <= c:
                        tri = True
                    elif lo > c:
                        tri = False
                if tri is False:
                    return False
                if tri is None:
                    result = None
            return result

        def refine_with_atoms(atoms, st):
            # 가드로 상태를 좁힘. 불가능이면 None
            if not atoms: return dict(st)
            cur = dict(st)
            for var, op, c in atoms:
                lo, hi = cur.get(var, as_point(0.0))
                if op == "==":
                    new_iv = meet_interval((lo, hi), lower=c, upper=c)
                elif op == "!=":
                    if lo == hi == c: return None
                    new_iv = (lo, hi)
                elif op == ">":
                    new_iv = meet_interval((lo, hi), lower=c, open_lower=True)
                elif op == ">=":
                    new_iv = meet_interval((lo, hi), lower=c)
                elif op == "<":
                    new_iv = meet_interval((lo, hi), upper=c, open_upper=True)
                elif op == "<=":
                    new_iv = meet_interval((lo, hi), upper=c)
                else:
                    return None
                if new_iv is None: return None
                cur[var] = new_iv
            return cur

        def eval_atoms_concrete(atoms, valuation):
            if atoms is None: return None
            for var, op, c in atoms:
                v = valuation.get(var, 0.0)
                if op == "==":
                    ok = (v == c)
                elif op == "!=":
                    ok = (v != c)
                elif op == ">":
                    ok = (v > c)
                elif op == ">=":
                    ok = (v >= c)
                elif op == "<":
                    ok = (v < c)
                elif op == "<=":
                    ok = (v <= c)
                else:
                    ok = False
                if not ok: return False
            return True

        # 액션
        def apply_actions_interval(pre_state, actions):
            st = dict(pre_state)
            for act in actions:
                var = act.var
                val = act.value
                if isinstance(val, bool): val = int(val)
                cur = st.get(var, as_point(0.0))
                if act.op == "set":
                    st[var] = as_point(val)
                elif act.op == "add":
                    lo, hi = cur;
                    st[var] = (lo + val, hi + val)
                elif act.op == "sub":
                    lo, hi = cur;
                    st[var] = (lo - val, hi - val)
                else:
                    st[var] = widen_unknown(cur)
            return st

        def apply_actions_concrete(valuation, actions):
            v = dict(valuation)
            for act in actions:
                var = act.var
                a = v.get(var, 0.0)
                b = act.value
                if isinstance(b, bool): b = int(b)
                if act.op == "set":
                    v[var] = float(b)
                elif act.op == "add":
                    v[var] = float(a + b)
                elif act.op == "sub":
                    v[var] = float(a - b)
                elif act.op == "mul":
                    v[var] = float(a * b)
                elif act.op == "div":
                    try:
                        v[var] = float(a / b)
                    except Exception:
                        v[var] = float('inf') if a >= 0 else float('-inf')
                elif act.op == "floordiv":
                    try:
                        v[var] = float(a // b)
                    except Exception:
                        v[var] = float('inf') if a >= 0 else float('-inf')
                elif act.op == "mod":
                    try:
                        v[var] = float(a % b)
                    except Exception:
                        v[var] = 0.0
                elif act.op == "pow":
                    try:
                        v[var] = float(a ** b)
                    except Exception:
                        v[var] = float('inf')
                else:
                    v[var] = a
            return v

        # 엣지(가드) 준비
        edges = {}
        for bid, br in branches.items():
            lst = []
            for ch in br.choices:
                atoms = parse_condition(ch.condition or "")
                lst.append((ch, atoms))
            edges[bid] = lst

        # 2) 고정점 전파(가드로 필터)
        initial = {k: as_point(int(v) if isinstance(v, bool) else v) for k, v in story.variables.items()}
        pre_state = {bid: None for bid in branches.keys()}
        post_state = {bid: None for bid in branches.keys()}

        pre_state[start_id] = dict(initial)
        work = [start_id]
        iter_count = {bid: 0 for bid in branches.keys()}
        LIMIT = max(200, 10 * max(1, len(branches)))

        while work and sum(iter_count.values()) < LIMIT:
            bid = work.pop()
            iter_count[bid] += 1
            br = branches[bid]
            cur_pre = pre_state[bid] or {}
            cur_post = apply_actions_interval(cur_pre, br.actions)

            # post join
            if post_state[bid] is None:
                post_state[bid] = cur_post
            else:
                merged = {}
                keys = set(post_state[bid].keys()) | set(cur_post.keys())
                for k in keys:
                    a = post_state[bid].get(k, as_point(0.0))
                    b = cur_post.get(k, as_point(0.0))
                    merged[k] = join_interval(a, b)
                post_state[bid] = merged

            # 전파
            for ch, atoms in edges[bid]:
                tgt = ch.target_id
                if tgt not in branches: continue
                if atoms is None:
                    filtered = dict(post_state[bid])  # 복잡식: 필터 없이 전파
                else:
                    filtered = refine_with_atoms(atoms, post_state[bid])
                if filtered is None: continue

                if pre_state[tgt] is None:
                    pre_state[tgt] = filtered
                    work.append(tgt)
                else:
                    merged = {}
                    changed = False
                    keys = set(pre_state[tgt].keys()) | set(filtered.keys())
                    for k in keys:
                        a = pre_state[tgt].get(k, as_point(0.0))
                        b = filtered.get(k, as_point(0.0))
                        m = join_interval(a, b)
                        merged[k] = m
                        if m != a: changed = True
                    if changed:
                        pre_state[tgt] = merged
                        work.append(tgt)

        # 3) SCC
        graph = {bid: [c.target_id for c in br.choices if c.target_id in branches] for bid, br in branches.items()}

        index = {};
        lowlink = {};
        stack = [];
        onstack = set();
        cur_idx = [0];
        scc_list = []

        def strongconnect(v):
            index[v] = cur_idx[0];
            lowlink[v] = cur_idx[0];
            cur_idx[0] += 1
            stack.append(v);
            onstack.add(v)
            for w in graph.get(v, []):
                if w not in index:
                    strongconnect(w);
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in onstack:
                    lowlink[v] = min(lowlink[v], index[w])
            if lowlink[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop();
                    onstack.remove(w);
                    comp.append(w)
                    if w == v: break
                scc_list.append(comp)

        for v in graph.keys():
            if v not in index:
                strongconnect(v)

        reachable = {b for b, st in pre_state.items() if st is not None}

        def label_of(bid):
            br = branches[bid]
            ch = story.chapters.get(br.chapter_id)
            ch_title = ch.title if ch else br.chapter_id
            return f"{bid} | {br.title} @ {ch_title}"

        # 4) 판정 + 증거 경로
        definite = []
        witnessed = []  # (comp, path)
        possible = []

        def pick_mid(iv):
            lo, hi = iv
            if math.isinf(lo) or math.isinf(hi):
                if math.isinf(lo) and math.isinf(hi): return 0.0
                if math.isinf(lo):  return hi - 1.0
                return lo + 1.0
            return (lo + hi) / 2.0

        def build_initial_valuation(bid):
            st = post_state.get(bid) or pre_state.get(bid) or {}
            v = {}
            related = set()
            for nid in graph.keys():
                for ch, atoms in edges[nid]:
                    if atoms:
                        for var, _, _ in atoms: related.add(var)
                for a in branches[nid].actions:
                    related.add(a.var)
            for k in related:
                iv = st.get(k, as_point(0.0))
                v[k] = float(round(pick_mid(iv), 6))
            return v

        def try_witness_for_comp(comp, max_steps=400):
            related = set()
            for bid in comp:
                for ch, atoms in edges[bid]:
                    if atoms:
                        for var, _, _ in atoms: related.add(var)
                for a in branches[bid].actions:
                    related.add(a.var)
            related = sorted(list(related))

            def key_of(bid, val):
                return (bid, tuple(float(round(val.get(k, 0.0), 6)) for k in related))

            start_nodes = [b for b in comp if b in reachable]
            if not start_nodes: return None
            start = start_nodes[0]
            val = build_initial_valuation(start)
            seen = set();
            path = [];
            cur = start;
            steps = 0
            while steps < max_steps:
                steps += 1
                sig = key_of(cur, val)
                if sig in seen: return path
                seen.add(sig)
                br = branches[cur]
                candidates = []
                for ch, atoms in edges[cur]:
                    if ch.target_id in comp:
                        ok = eval_atoms_concrete(atoms, val) if atoms is not None else True
                        if ok or atoms is None: candidates.append((ch, atoms))
                if not candidates: return None
                ch, atoms = candidates[0]
                val = apply_actions_concrete(val, br.actions)
                path.append((br.branch_id, ch.text, ch.target_id))
                cur = ch.target_id
            return None

        for comp in scc_list:
            # 루프 아님 필터
            if len(comp) == 1:
                only = comp[0]
                self_loop = any((c.target_id == only) for c in branches[only].choices)
                if not self_loop: continue
            if not any(b in reachable for b in comp): continue

            all_nodes_have_internal_always = True
            any_external_satisfiable = False
            all_nodes_have_internal_possible = True

            for bid in comp:
                br = branches[bid]
                pst = post_state[bid] or pre_state[bid] or {}
                internal_always = False
                internal_possible = False
                external_satisfy = False

                for ch, atoms in edges[bid]:
                    if atoms is None:
                        cond_every = None
                        cond_sat = True
                    else:
                        cond_every = eval_atoms_over_interval(atoms, pst)
                        cond_sat = refine_with_atoms(atoms, pst) is not None

                    if ch.target_id in comp:
                        if cond_every is True:
                            internal_always = True
                            internal_possible = True
                        elif cond_sat:
                            internal_possible = True
                    else:
                        if cond_sat:
                            external_satisfy = True

                if not internal_always:
                    all_nodes_have_internal_always = False
                if not internal_possible:
                    all_nodes_have_internal_possible = False
                if external_satisfy:
                    any_external_satisfiable = True

            if all_nodes_have_internal_always and not any_external_satisfiable:
                definite.append(comp)
            else:
                w = try_witness_for_comp(comp)
                if w:
                    witnessed.append((comp, w))
                elif all_nodes_have_internal_possible:
                    possible.append(comp)

        # 5) 간결 리포트 생성
        def nodes_summary(comp, limit=6):
            labels = [label_of(b) for b in comp]
            if len(labels) <= limit:
                return " → ".join(labels)
            return " → ".join(labels[:limit]) + f" … (+{len(labels) - limit})"

        def exit_edges_summary(comp, max_list=3):
            # comp 바깥으로 나가는 엣지 3개까지 요약: src -> tgt | 조건 | 판정
            items = []
            for bid in comp:
                br = branches[bid]
                pst = post_state[bid] or pre_state[bid] or {}
                for ch, atoms in edges[bid]:
                    if ch.target_id in comp: continue
                    if atoms is None:
                        verdict = tr("uncertain_complex")
                        cond_s = tr("complex_expr")
                    else:
                        every = eval_atoms_over_interval(atoms, pst)
                        cond_s = " and ".join(f"{v} {op} {val}" for (v, op, val) in atoms) if atoms else tr("cond_none")
                        if every is True:
                            verdict = tr("always_open")
                        else:
                            sat = refine_with_atoms(atoms, pst) is not None
                            verdict = tr("possible") if sat else tr("impossible")
                    items.append(f"{bid} → {ch.target_id} | {cond_s} | {verdict}")
            if not items: return tr("no_exit_path")
            if len(items) > max_list:
                return "\n".join(items[:max_list] + [tr("more_items", n=len(items) - max_list)])
            return "\n".join(items)

        lines = []
        lines.append(tr("loop_summary_heading"))
        lines.append("")
        lines.append(tr("loop_summary_counts", definite=len(definite), witnessed=len(witnessed), possible=len(possible)))
        lines.append("")

        if definite:
            lines.append(tr("loop_definite_header"))
            for i, comp in enumerate(definite, 1):
                lines.append(tr("loop_nodes_line", i=i, count=len(comp)))
                lines.append(tr("loop_path_summary_line", path=nodes_summary(comp)))
                lines.append(tr("loop_no_exit"))
                lines.append(tr("loop_definite_action"))
                lines.append("")
        if witnessed:
            lines.append(tr("loop_witnessed_header"))
            for i, (comp, path) in enumerate(witnessed, 1):
                lines.append(tr("loop_nodes_line", i=i, count=len(comp)))
                lines.append(tr("loop_path_summary_line", path=nodes_summary(comp)))
                lines.append(tr("loop_example_path"))
                for step in path[:12]:
                    src_bid, text, tgt_bid = step
                    lines.append(f"     {src_bid} --[{text}]--> {tgt_bid}")
                if len(path) > 12:
                    lines.append(tr("loop_more_steps", count=len(path) - 12))
                ex = exit_edges_summary(comp, max_list=2)
                lines.append(tr("loop_exit_candidates"))
                for ln in ex.split("\n"):
                    lines.append("     " + ln)
                lines.append(tr("loop_witnessed_action"))
                lines.append("")
        if possible:
            lines.append(tr("loop_possible_header"))
            for i, comp in enumerate(possible, 1):
                lines.append(tr("loop_nodes_line", i=i, count=len(comp)))
                lines.append(tr("loop_path_summary_line", path=nodes_summary(comp)))
                ex = exit_edges_summary(comp, max_list=3)
                lines.append(tr("loop_exit_summary"))
                for ln in ex.split("\n"):
                    lines.append("     " + ln)
                lines.append(tr("loop_possible_action"))
                lines.append("")

        lines.append(tr("definitions_heading"))
        lines.append(tr("definition_definite"))
        lines.append(tr("definition_witnessed"))
        lines.append(tr("definition_possible"))

        # 팝업 표시
        win = tk.Toplevel(self)
        win.title(tr("loop_analysis_title"))
        win.geometry("900x560")
        frm = ttk.Frame(win, padding=8)
        frm.pack(fill="both", expand=True)

        txt = tk.Text(frm, wrap="word", font=("Consolas", 10))
        txt.pack(side="left", fill="both", expand=True)
        scr = ttk.Scrollbar(frm, orient="vertical", command=txt.yview)
        scr.pack(side="right", fill="y")
        txt.configure(yscrollcommand=scr.set)
        txt.insert(tk.END, "\n".join(lines))
        txt.configure(state="disabled")

        ttk.Button(win, text=tr("close"), command=win.destroy).pack(pady=6)


# ---------- 진입점 ----------

def main():
    parser = argparse.ArgumentParser(description="Branching Novel Editor")
    parser.add_argument("--lang", help="language code (e.g., en, ko)")
    args = parser.parse_args()

    if args.lang:
        set_language(args.lang)
    else:
        lang_file = os.path.join(os.path.dirname(__file__), "editor_language.txt")
        set_language_from_file(lang_file)

    app = ChapterEditor()
    check_for_update(APP_NAME, INSTALLER_NAME, parent=app)
    app.mainloop()

if __name__ == "__main__":
    main()
