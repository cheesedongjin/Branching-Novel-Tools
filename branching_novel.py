"""
Branching Novel GUI (Interactive Fiction with Simple Text Syntax)

- 요구사항
  1) 소설은 텍스트 파일로 분기별로 정의.
  2) 간단한 문법을 파싱하여 게임 소설을 쓸 수 있음.
  3) 파이썬 인자로 첫 텍스트 파일을 읽어 GUI를 실행.
  4) 선택에 따라 "앞/뒤"로 넘길 수 있는 책처럼 감상 가능(방문 경로를 히스토리로 관리).
  5) 챕터 목록 표시.

- 사용법
  python branching_novel.py path/to/story.bnov
  (인자를 생략하면 파일 선택 대화상자가 열림)

- 파일 문법
  메타데이터(선택):
    @title: 작품 제목
    @start: 시작 챕터ID

  챕터 선언:
    # chapter_id: Chapter Title
    본문 문단...
    빈 줄은 문단 구분.
    선택지는 다음 형식:
      * 버튼에 보일 문장 -> 다음_챕터ID
    문단과 선택지 사이의 순서는 자유. 선택지가 여러 개면 여러 줄로 나열.

  예시:
    @title: 밤비
    @start: intro

    # intro: 창밖의 이름
    밤비는 창문을 열고 한숨을 내쉬었다.
    어둠 속에서 누군가 그녀의 이름을 불렀다.

    * 창밖을 확인한다 -> alley
    * 대답하지 않는다 -> silence
    * 문을 걸어 잠근다 -> lock

    # alley: 골목의 남자
    그녀는 조심스레 창문을 열어젖혔다.
    서늘한 밤공기가 흘러들었다. 골목 아래, 낯선 남자가 서 있었다.

    * 그를 부른다 -> call
    * 창문을 닫는다 -> lock

- 설계 요약
  1) Parser: StoryParser
     - @title, @start 처리
     - # id: Title 로 챕터 정의
     - 본문은 연속 줄을 문단으로 모으고, 빈 줄로 문단 경계
     - 선택지 라인은 "* text -> target" 형식으로 파싱
  2) Data Model
     - Story: title, start_id, chapters(dict[str, Chapter])
     - Chapter: id, title, paragraphs(list[str]), choices(list[Choice])
     - Choice: text, target_id
  3) GUI
     - 좌측: Chapter List (Listbox)
     - 우측 상단: 제목/경로/네비게이션(처음, 이전, 다음)
     - 우측 중앙: 본문(Text, 읽기 전용, 스크롤)
     - 우측 하단: 선택지 버튼들
     - 히스토리: 사용자의 경로를 Step 단위로 저장
       Step = {chapter_id, chosen_text(optional)}
       '다음'은 히스토리에서 앞 항목으로 이동, '이전'은 뒤로
       과거로 돌아가 새 선택을 하면 해당 시점 이후 히스토리를 잘라내어 새로운 경로 생성
  4) 챕터 목록 클릭
     - 리스트에서 챕터를 더블클릭하면 그 챕터로 점프
     - 점프 시 현재 위치 이후 히스토리를 절단하고 새 경로로 이어짐

- 주의
  - ASCII 아트나 이모티콘은 사용하지 않음.
  - 외부 라이브러리 없음. Tkinter 표준만 사용.
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
    """기존 챕터에 해당하는 세부 분기"""

    branch_id: str
    title: str
    chapter_id: str = ""
    paragraphs: List[str] = field(default_factory=list)
    choices: List[Choice] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)


@dataclass
class Chapter:
    """여러 분기(Branch)를 담는 상위 단위"""

    chapter_id: str
    title: str
    branches: Dict[str, Branch] = field(default_factory=dict)


@dataclass
class Story:
    title: str = "Untitled"
    start_id: Optional[str] = None  # 시작 분기 ID
    ending_text: str = "The End"
    chapters: Dict[str, Chapter] = field(default_factory=dict)
    branches: Dict[str, Branch] = field(default_factory=dict)
    variables: Dict[str, Union[int, float, bool]] = field(default_factory=dict)

    def get_branch(self, bid: str) -> Optional[Branch]:
        return self.branches.get(bid)

    def get_chapter(self, cid: str) -> Optional[Chapter]:
        return self.chapters.get(cid)


class ParseError(Exception):
    pass


class StoryParser:
    """
    간단한 문법 파서
    - 주석은 지원하지 않음. 비어 있는 줄은 문단 구분.
    - 한 챕터 내부에서는 본문 줄과 선택지 라인이 섞여 있어도 됨.
    - 선택지 라인은 "* "로 시작하고 "->"를 포함해야 함.
    """

    def parse(self, text: str) -> Story:
        text = text.lstrip("\ufeff")
        lines = [ln.lstrip("\ufeff") for ln in text.splitlines()]
        story = Story()
        current_chapter: Optional[Chapter] = None
        current_branch: Optional[Branch] = None
        paragraph_buffer: List[str] = []

        # 메타데이터 임시 저장
        for idx, raw in enumerate(lines):
            line = raw.strip()

            # 메타데이터 처리
            if line.startswith("@title:"):
                story.title = line[len("@title:"):].strip() or "Untitled"
                continue
            if line.startswith("@start:"):
                story.start_id = line[len("@start:"):].strip() or None
                continue
            if line.startswith("@ending:"):
                story.ending_text = line[len("@ending:"):].strip() or "The End"
                continue

        # 실제 파싱 루프
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip("\n")
            stripped = line.strip()
            i += 1

            if stripped.startswith("@chapter"):
                # 챕터 선언
                current_branch = None
                current_chapter = self._parse_chapter_decl(stripped)
                if current_chapter.chapter_id in story.chapters:
                    raise ParseError(f"Duplicate chapter id: {current_chapter.chapter_id}")
                story.chapters[current_chapter.chapter_id] = current_chapter
                continue

            # 기타 메타데이터는 1차 루프에서 처리했으므로 건너뛴다
            if (
                stripped.startswith("@title:")
                or stripped.startswith("@start:")
                or stripped.startswith("@ending:")
            ):
                continue

            # 분기 시작
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

            # 빈 줄은 문단 경계로 처리
            if stripped == "":
                if current_branch is not None:
                    merged = self._merge_paragraph_buffer(paragraph_buffer)
                    current_branch.paragraphs.extend(merged)
                    paragraph_buffer.clear()
                continue

            # 상태 변경 지시문
            if stripped.startswith("!"):
                action = self._parse_action_line(stripped)
                if current_branch is None:
                    if action.op != "set":
                        raise ParseError("State change found outside of any branch.")
                    story.variables[action.var] = action.value
                else:
                    current_branch.actions.append(action)
                continue

            # 선택지 라인
            if stripped.startswith("* "):
                if current_branch is None:
                    raise ParseError("Choice found outside of any branch.")
                choice = self._parse_choice_line(stripped)
                current_branch.choices.append(choice)
                continue

            # 일반 본문 라인
            if current_branch is None:
                raise ParseError("Found narrative text outside of a branch. Add a branch header starting with '#'.")
            paragraph_buffer.append(line)

        # 파일 끝 처리
        if current_branch is not None and paragraph_buffer:
            merged = self._merge_paragraph_buffer(paragraph_buffer)
            current_branch.paragraphs.extend(merged)
            paragraph_buffer.clear()

        # 시작 분기가 명시되지 않았다면 첫 분기를 시작으로
        if story.start_id is None:
            if story.branches:
                story.start_id = next(iter(story.branches.keys()))
            else:
                raise ParseError("No branches found in story.")

        # 타겟 유효성 경고를 위한 기본 검사(존재하지 않는 타겟은 실행 중에도 확인)
        return story

    def _merge_paragraph_buffer(self, buffer: List[str]) -> List[str]:
        """
        연속된 본문 라인들을 빈 줄 기준으로 문단 리스트로 변환.
        이미 상위에서 빈 줄이 들어오면 플러시하므로 여기서는 버퍼 전체를 문단 하나로도 볼 수 있음.
        다만 자연스러운 단락 구분을 위해 빈 줄이 포함되어 들어온 경우도 처리.
        """
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
        """형식: '@chapter id: Title' 또는 '@chapter id'"""
        content = line[len("@chapter"):].strip()
        if ":" in content:
            cid, title = content.split(":", 1)
            return Chapter(chapter_id=cid.strip(), title=title.strip())
        return Chapter(chapter_id=content.strip(), title=content.strip())

    def _parse_branch_header(self, header_line: str, chapter_id: str) -> Branch:
        """형식: '# id: Title' 또는 '# id'"""
        content = header_line.lstrip("#").strip()
        if ":" in content:
            bid, title = content.split(":", 1)
            return Branch(branch_id=bid.strip(), title=title.strip(), chapter_id=chapter_id)
        else:
            bid = content.strip()
            return Branch(branch_id=bid, title=bid, chapter_id=chapter_id)

    def _parse_choice_line(self, line: str) -> Choice:
        """
        형식: "* [조건] text -> target_id" 또는 "* text -> target_id"
        """
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

        self.btn_home = ttk.Button(btn_frame, text="처음부터", command=self._confirm_reset)
        self.btn_home.grid(row=0, column=0, padx=4)
        ttk.Label(btn_frame, text="← →").grid(row=0, column=1, padx=4)

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
        self.chapter_list.delete(0, tk.END)
        for cid in self.visited_chapters:
            ch = self.story.get_chapter(cid)
            title = ch.title if ch and ch.title else cid
            self.chapter_list.insert(tk.END, f"{cid}  |  {title}")

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
            "경고", "지금까지의 진행 상황이 사라집니다.\n처음부터 다시 시작하시겠습니까?"
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
            messagebox.showerror("오류", "시작 분기가 유효하지 않습니다.")
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
        text = "\n".join(lines) if lines else "(내용 없음)"
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
        self.text_widget.see("1.0")

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
            exit_btn = ttk.Button(self.choice_frame, text="나가기", command=self.destroy)
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
            messagebox.showerror("오류", f"타겟 분기가 존재하지 않습니다: {choice.target_id}")
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
        pass

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
        for i in range(self.chapter_list.size()):
            item = self.chapter_list.get(i)
            item_cid = item.split("|", 1)[0].strip()
            if item_cid == cid:
                self.chapter_list.selection_clear(0, tk.END)
                self.chapter_list.selection_set(i)
                self.chapter_list.see(i)
                break

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
        expr = re.sub(r"\btrue\b", "True", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bfalse\b", "False", expr, flags=re.IGNORECASE)
        try:
            tree = ast.parse(expr, mode="exec")
            result = self._eval_ast(tree)
            return bool(result)
        except Exception:
            return False

    def _eval_ast(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Module):
            result = None
            for stmt in node.body:
                result = self._eval_ast(stmt)
            return result
        elif isinstance(node, ast.Expr):
            return self._eval_ast(node.value)
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("Unsupported assignment")
            val = self._eval_ast(node.value)
            self.state[node.targets[0].id] = val
            return val
        elif isinstance(node, ast.AugAssign):
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
                raise ValueError("Unsupported assignment")
            return self.state[target]
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for v in node.values:
                    if not self._eval_ast(v):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for v in node.values:
                    if self._eval_ast(v):
                        return True
                return False
            else:
                raise ValueError("Unsupported boolean operator")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_ast(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
            elif isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
            else:
                raise ValueError("Unsupported unary operator")
        elif isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            elif isinstance(node.op, ast.FloorDiv):
                return left // right
            elif isinstance(node.op, ast.Mod):
                return left % right
            elif isinstance(node.op, ast.Pow):
                return left ** right
            else:
                raise ValueError("Unsupported binary operator")
        elif isinstance(node, ast.Compare):
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
        elif isinstance(node, ast.Name):
            return self.state.get(node.id, 0)
        elif isinstance(node, ast.Constant):
            return node.value
        else:
            raise ValueError("Unsupported expression")

    def _to_python_expr(self, cond: str) -> str:
        result = []
        i = 0
        while i < len(cond):
            ch = cond[i]
            if ch == '!':
                if i + 1 < len(cond) and cond[i + 1] == '=':
                    result.append('!=')
                    i += 2
                else:
                    result.append(' not ')
                    i += 1
            elif ch == '&':
                result.append(' and ')
                i += 1
            elif ch == '|':
                result.append(' or ')
                i += 1
            else:
                result.append(ch)
                i += 1
        return ''.join(result)


def load_text_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="Branching Novel GUI")
    parser.add_argument("file", nargs="?", help="Story file path (.bnov)")
    parser.add_argument("--show-disabled", action="store_true", help="Show unavailable choices as disabled")
    args = parser.parse_args()

    file_path = args.file
    if not file_path:
        # 파일 선택 대화상자
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="소설 파일 선택",
            filetypes=[("Branching Novel Files", "*.bnov"), ("All Files", "*.*")]
        )
        root.destroy()
        if not file_path:
            return

    if not os.path.isfile(file_path):
        print("파일을 찾을 수 없습니다:", file_path)
        sys.exit(1)

    try:
        text = load_text_from_file(file_path)
        parser = StoryParser()
        story = parser.parse(text)
    except ParseError as e:
        messagebox.showerror("파싱 오류", str(e))
        sys.exit(1)
    except Exception as e:
        messagebox.showerror("오류", f"파일을 읽는 중 오류가 발생했습니다:\n{e}")
        sys.exit(1)

    app = BranchingNovelApp(story, file_path, show_disabled=args.show_disabled)
    app.mainloop()


if __name__ == "__main__":
    main()
