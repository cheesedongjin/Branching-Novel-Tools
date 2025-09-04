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
import re
import ast
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union, Any
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from i18n import tr, set_language, set_language_from_file

from auto_update import check_for_update
from story_parser import Choice, Action, Branch, Chapter, Story, ParseError, StoryParser


APP_NAME = "Branching Novel GUI"
INSTALLER_NAME = "BranchingNovelGUI-Online-Setup.exe"


@dataclass
class Step:
    """
    A step in the history. Records branch_id and the text chosen by the user.
    The branch may have no choices, so chosen_text is optional.
    """
    branch_id: str
    chosen_text: Optional[str] = None


class BranchingNovelApp(tk.Tk):
    """
    Tkinter-based GUI application
    """

    def __init__(self, story: Story, file_path: str, show_disabled: bool = False):
        super().__init__()
        self.title(f"{story.title} - Branching Novel")
        self.geometry("1000x700")

        self.story = story
        self.file_path = file_path

        # state values and options
        self.show_disabled = show_disabled
        self.state: Dict[str, Union[int, float, bool, str]] = {}

        # history and current index
        self.history: List[Step] = []
        self.current_index: int = -1  # current branch index in history
        self.visited_chapters: List[str] = []
        self.chapter_positions: List[int] = []  # start index of each chapter
        self.chapter_page_index: int = -1

        self._build_ui()
        self._bind_events()

        # move to starting chapter
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
            title = self._interpolate(ch.title) if ch and ch.title else ""
            item = f"{cid} | {title}" if title else cid
            self.chapter_list.insert(tk.END, item)
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
                lines.append("\n".join(self._interpolate(p) for p in br.paragraphs))
            if i + 1 < end and step.chosen_text:
                lines.append(f"> {step.chosen_text}")
        text = "\n".join(lines) if lines else tr("no_content")
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
        title = self._interpolate(self.story.title)
        self.title(f"{title} - Branching Novel")
        self.title_label.configure(text=title)
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
            lbl = ttk.Label(self.choice_frame, text=self._interpolate(self.story.ending_text))
            lbl.grid(row=0, column=0, sticky="w")
            exit_btn = ttk.Button(self.choice_frame, text=tr("exit"), command=self.destroy)
            exit_btn.grid(row=1, column=0, sticky="ew", pady=2)
            return

        # 버튼 생성
        for idx, (choice, disabled) in enumerate(display, 1):
            txt = self._interpolate(choice.text)
            btn = ttk.Button(self.choice_frame, text=f"{idx}. {txt}",
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
            cur.chosen_text = self._interpolate(choice.text)
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
            name = self._interpolate(br.title) if br and br.title else step.branch_id
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

    def _compute_state(self, upto_index: int) -> Dict[str, Union[int, float, bool, str]]:
        state: Dict[str, Union[int, float, bool, str]] = dict(self.story.variables)
        for i in range(0, upto_index + 1):
            step = self.history[i]
            br = self.story.get_branch(step.branch_id)
            if not br:
                continue
            for act in br.actions:
                cur = state.get(act.var, 0)
                val = act.value
                if act.op != "set":
                    if isinstance(cur, bool):
                        cur = int(cur)
                    if isinstance(val, bool):
                        val = int(val)
                if act.op == "set":
                    state[act.var] = val
                elif act.op == "expr":
                    expr = self._to_python_expr(str(val))
                    try:
                        state[act.var] = eval(expr, {}, dict(state))
                    except Exception:
                        state[act.var] = 0
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

    def _interpolate(self, text: str) -> str:
        if not text:
            return ""

        result = []
        i = 0
        while i < len(text):
            if text.startswith("__", i):
                j = text.find("__", i + 2)
                name = text[i + 2 : j] if j != -1 else ""
                if j != -1 and name and re.fullmatch(r"[A-Za-z0-9_]+", name):
                    token = f"__{name}__"
                    if token in self.state:
                        result.append(str(self.state[token]))
                    elif token in self.story.variables:
                        result.append(str(self.story.variables[token]))
                    else:
                        result.append(token)
                    i = j + 2
                    continue
                result.append("__")
                i += 2
            else:
                result.append(text[i])
                i += 1

        return "".join(result)

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
        lang_file = os.path.join(os.path.dirname(__file__), "game_language.txt")
        set_language_from_file(lang_file)

    file_path = args.file
    if not file_path:
        # 파일 선택 대화상자
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
    check_for_update(APP_NAME, INSTALLER_NAME, parent=app)
    app.mainloop()


if __name__ == "__main__":
    main()
