"""
Branching Novel Editor (GUI)

이 에디터는 하나의 "챕터" 안에 여러 "분기"(branch)를 배치하는 최신 문법을
완전히 지원합니다. 분기들은 기존 챕터와 동일한 역할을 하며, 챕터는 책의 한 장처럼
여러 분기를 묶는 큰 단위입니다.

문법 포맷:
  @title: 작품 제목
  @start: 시작분기ID

  @chapter chapter_id: Chapter Title
  # branch_id: Branch Title
  본문 문단1

  본문 문단2

  * 버튼 문구 -> target_branch_id
  * 버튼 문구2 -> target_branch_id2

주의:
  - 챕터 id와 분기 id는 각각 전역에서 고유해야 함.
  - 선택지 타깃은 존재하지 않는 분기를 가리킬 수도 있으나, 저장 전 유효성 경고 제공.
  - 본문은 에디터에서 빈 줄로 문단 구분.

사용법:
  python branching_novel_editor.py
"""

import os
import sys
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union

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

        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip("\n")
            stripped = line.strip()
            i += 1

            if stripped.startswith(("@title:", "@start:", "@ending:")):
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

# ---------- 에디터 GUI ----------

class ConditionRowDialog(tk.Toplevel):
    def __init__(self, master, variables: List[str], initial: Optional[Tuple[str, str, str]]):
        super().__init__(master)
        self.title("조건/행동")
        self.resizable(False, False)
        self.result_ok = False
        self.condition: Optional[Tuple[str, str, str]] = None

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="변수").grid(row=0, column=0, sticky="w")
        self.cmb_var = ttk.Combobox(frm, values=variables, state="readonly", width=20)
        self.cmb_var.grid(row=1, column=0, sticky="ew", pady=(0,8))

        ttk.Label(frm, text="연산자").grid(row=0, column=1, sticky="w", padx=(8,0))
        ops = ["==", "!=", ">", "<", ">=", "<=", "=", "+=", "-=", "*=", "/=", "//=", "%=", "**="]
        self.cmb_op = ttk.Combobox(frm, values=ops, state="readonly", width=7)
        self.cmb_op.grid(row=1, column=1, sticky="w", padx=(8,0))

        ttk.Label(frm, text="값").grid(row=0, column=2, sticky="w", padx=(8,0))
        self.ent_val = ttk.Entry(frm, width=15)
        self.ent_val.grid(row=1, column=2, sticky="ew", padx=(8,0))

        help_text = (
            "연산자 표:\n"
            "=  : 대입\n"
            "+= : 더해서 대입, -= : 빼서 대입, *= : 곱해서 대입, /= : 나누어 대입\n"
            "//= : 몫만 대입, %= : 나머지 대입, **= : 거듭제곱 대입\n"
            "== : 같음, != : 다름, > : 큼, < : 작음, >= : 크거나 같음, <= : 작거나 같음"
        )
        ttk.Label(frm, text=help_text, justify="left").grid(row=2, column=0, columnspan=3, sticky="w", pady=(8,0))

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=3, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text="확인", command=self._ok)
        cancel = ttk.Button(btns, text="취소", command=self._cancel)
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
            messagebox.showerror("오류", "변수, 연산자, 값을 모두 입력하세요.")
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
        self.title("변수 추가" if not name else "변수 편집")
        self.resizable(False, False)
        self.result_ok = False
        self.var_name: str = name
        self.value: Union[int, float, bool] = value if value is not None else 0

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="변수명").grid(row=0, column=0, sticky="w")
        self.ent_name = ttk.Entry(frm, width=20)
        self.ent_name.grid(row=1, column=0, sticky="ew", pady=(0,8))
        if name:
            self.ent_name.insert(0, name)

        ttk.Label(frm, text="초기값").grid(row=0, column=1, sticky="w", padx=(8,0))
        self.ent_val = ttk.Entry(frm, width=10)
        self.ent_val.grid(row=1, column=1, sticky="ew", padx=(8,0))
        if value is not None:
            self.ent_val.insert(0, str(value).lower() if isinstance(value, bool) else str(value))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text="확인", command=self._ok)
        cancel = ttk.Button(btns, text="취소", command=self._cancel)
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
            messagebox.showerror("오류", "변수명과 초기값을 입력하세요.")
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
                    messagebox.showerror("오류", "초기값은 숫자 또는 true/false여야 합니다.")
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
        self.title("조건/행동 편집")
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
        self.tree.heading("var", text="변수")
        self.tree.heading("op", text="연산자")
        self.tree.heading("val", text="값")
        self.tree.column("var", width=100, anchor="w")
        self.tree.column("op", width=80, anchor="w")
        self.tree.column("val", width=120, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        btns = ttk.Frame(frm)
        btns.grid(row=0, column=1, sticky="ns", padx=(8,0))
        ttk.Button(btns, text="추가", command=self._add).grid(row=0, column=0, pady=2)
        ttk.Button(btns, text="편집", command=self._edit).grid(row=1, column=0, pady=2)
        ttk.Button(btns, text="삭제", command=self._delete).grid(row=2, column=0, pady=2)
        ttk.Button(btns, text="변수 추가", command=self._add_variable).grid(row=3, column=0, pady=2)

        bottom = ttk.Frame(frm)
        bottom.grid(row=1, column=0, columnspan=2, sticky="e", pady=(8,0))
        ok = ttk.Button(bottom, text="확인", command=self._ok)
        cancel = ttk.Button(bottom, text="취소", command=self._cancel)
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

        ttk.Label(frm, text="버튼 문구").grid(row=0, column=0, sticky="w")
        self.ent_text = ttk.Entry(frm, width=50)
        self.ent_text.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,8))

        ttk.Label(frm, text="이동 타깃 분기 ID").grid(row=2, column=0, sticky="w")
        self.cmb_target = ttk.Combobox(frm, values=branch_ids, state="readonly", width=30)
        self.cmb_target.grid(row=3, column=0, sticky="w")

        ttk.Label(frm, text="조건/행동식").grid(row=4, column=0, sticky="w")
        cond_frame = ttk.Frame(frm)
        cond_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0,8))
        cond_frame.columnconfigure(0, weight=1)
        self.ent_cond = ttk.Entry(cond_frame, width=50, state="readonly")
        self.ent_cond.grid(row=0, column=0, sticky="ew")
        ttk.Button(cond_frame, text="편집...", command=self._open_cond_editor).grid(row=0, column=1, padx=(4,0))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text="확인", command=self._ok)
        cancel = ttk.Button(btns, text="취소", command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        if choice:
            self.ent_text.insert(0, choice.text)
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
        text = self.ent_text.get().strip()
        target = self.cmb_target.get().strip()
        cond = self.ent_cond.get().strip()
        cond = re.sub(r"\btrue\b", "1", cond, flags=re.IGNORECASE)
        cond = re.sub(r"\bfalse\b", "0", cond, flags=re.IGNORECASE)
        if not text:
            messagebox.showerror("오류", "버튼 문구를 입력하세요.")
            return
        if not target:
            messagebox.showerror("오류", "이동 타깃 분기 ID를 선택하세요.")
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
        fm.add_command(label="새로 만들기", command=self._new_story, accelerator="Ctrl+N")
        fm.add_command(label="열기...", command=self._open_file, accelerator="Ctrl+O")
        fm.add_separator()
        fm.add_command(label="저장", command=self._save_file, accelerator="Ctrl+S")
        fm.add_command(label="다른 이름으로 저장...", command=self._save_file_as)
        fm.add_separator()
        fm.add_command(label="종료", command=self._exit_app)
        m.add_cascade(label="파일", menu=fm)

        em = tk.Menu(m, tearoff=0)
        em.add_command(label="챕터 추가", command=self._add_chapter, accelerator="Ctrl+Shift+A")
        em.add_command(label="챕터 삭제", command=self._delete_current_chapter, accelerator="Del")
        em.add_separator()
        em.add_command(label="찾기/변경", command=self._open_find_window, accelerator="Ctrl+F")
        m.add_cascade(label="편집", menu=em)

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
        meta = ttk.LabelFrame(left, text="작품 정보", padding=8)
        meta.grid(row=0, column=0, sticky="ew")
        meta.columnconfigure(1, weight=1)

        ttk.Label(meta, text="제목(@title)").grid(row=0, column=0, sticky="w")
        self.ent_title = ttk.Entry(meta, width=30)
        self.ent_title.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        self.ent_title.insert(0, self.story.title)
        self.ent_title.bind("<KeyRelease>", lambda e: self._on_title_changed())

        ttk.Label(meta, text="시작 분기(@start)").grid(row=1, column=0, sticky="w")
        self.cmb_start = ttk.Combobox(meta, values=[], state="readonly")
        self.cmb_start.grid(row=1, column=1, sticky="ew")
        self.cmb_start.bind("<<ComboboxSelected>>", lambda e: self._on_start_changed())

        ttk.Label(meta, text="엔딩 문구(@ending)").grid(row=2, column=0, sticky="w")
        self.ent_end = ttk.Entry(meta, width=30)
        self.ent_end.grid(row=2, column=1, sticky="ew")
        self.ent_end.insert(0, self.story.ending_text)
        self.ent_end.bind("<KeyRelease>", lambda e: self._on_ending_changed())

        # 변수 목록
        var_frame = ttk.LabelFrame(left, text="변수 목록", padding=8)
        var_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        var_frame.columnconfigure(0, weight=1)

        btns = ttk.Frame(var_frame)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text="추가", command=self._add_variable).pack(side="left")
        ttk.Button(btns, text="편집", command=self._edit_variable).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="삭제", command=self._delete_variable).pack(side="left", padx=(6, 0))

        self.tree_vars = ttk.Treeview(var_frame, columns=("var", "val"), show="headings", height=5)
        self.tree_vars.heading("var", text="변수")
        self.tree_vars.heading("val", text="값")
        self.tree_vars.column("var", width=80, anchor="w")
        self.tree_vars.column("val", width=80, anchor="w")
        self.tree_vars.grid(row=1, column=0, sticky="ew")

        # 챕터 목록
        chap_frame = ttk.LabelFrame(left, text="챕터 목록", padding=8)
        chap_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        chap_frame.rowconfigure(1, weight=1)
        chap_frame.columnconfigure(0, weight=1)

        self.lst_chapters = tk.Listbox(chap_frame, height=20, exportselection=False)
        self.lst_chapters.grid(row=1, column=0, sticky="nsew")
        self.lst_chapters.bind("<<ListboxSelect>>", lambda e: self._on_select_chapter())
        self.lst_chapters.bind("<Double-Button-1>", lambda e: self._on_select_chapter())

        btns = ttk.Frame(chap_frame)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text="추가", command=self._add_chapter).pack(side="left")
        ttk.Button(btns, text="삭제", command=self._delete_current_chapter).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="위로", command=lambda: self._reorder_chapter(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="아래로", command=lambda: self._reorder_chapter(1)).pack(side="left", padx=(6, 0))

        # 분기 목록
        branch_frame = ttk.LabelFrame(left, text="분기 목록", padding=8)
        branch_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        branch_frame.rowconfigure(1, weight=1)
        branch_frame.columnconfigure(0, weight=1)

        self.lst_branches = tk.Listbox(branch_frame, height=15, exportselection=False)
        self.lst_branches.grid(row=1, column=0, sticky="nsew")
        self.lst_branches.bind("<<ListboxSelect>>", lambda e: self._on_select_branch())
        self.lst_branches.bind("<Double-Button-1>", lambda e: self._on_select_branch())

        bbtns = ttk.Frame(branch_frame)
        bbtns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bbtns, text="추가", command=self._add_branch).pack(side="left")
        ttk.Button(bbtns, text="삭제", command=self._delete_current_branch).pack(side="left", padx=(6, 0))
        ttk.Button(bbtns, text="위로", command=lambda: self._reorder_branch(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(bbtns, text="아래로", command=lambda: self._reorder_branch(1)).pack(side="left", padx=(6, 0))

        # 우측 편집/미리보기 영역
        right = ttk.Notebook(root)
        right.grid(row=0, column=1, sticky="nsew")
        self.nb_right = right

        # 챕터 편집 탭
        edit_tab = ttk.Frame(right, padding=8)
        right.add(edit_tab, text="분기 편집")

        edit_tab.columnconfigure(1, weight=1)
        edit_tab.rowconfigure(4, weight=1)

        ttk.Label(edit_tab, text="챕터 ID").grid(row=0, column=0, sticky="w")
        self.ent_ch_id = ttk.Entry(edit_tab)
        self.ent_ch_id.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        self.ent_ch_id.bind("<FocusOut>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_id.bind("<Return>", lambda e: self._apply_chapter_id_title())

        ttk.Label(edit_tab, text="챕터 제목").grid(row=1, column=0, sticky="w")
        self.ent_ch_title = ttk.Entry(edit_tab)
        self.ent_ch_title.grid(row=1, column=1, sticky="ew", pady=(0, 6))
        self.ent_ch_title.bind("<FocusOut>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_title.bind("<Return>", lambda e: self._apply_chapter_id_title())

        ttk.Label(edit_tab, text="분기 ID").grid(row=2, column=0, sticky="w")
        self.ent_br_id = ttk.Entry(edit_tab)
        self.ent_br_id.grid(row=2, column=1, sticky="ew", pady=(0, 6))
        self.ent_br_id.bind("<FocusOut>", lambda e: self._apply_branch_id_title())
        self.ent_br_id.bind("<Return>", lambda e: self._apply_branch_id_title())

        ttk.Label(edit_tab, text="분기 제목").grid(row=3, column=0, sticky="w")
        self.ent_br_title = ttk.Entry(edit_tab)
        self.ent_br_title.grid(row=3, column=1, sticky="ew", pady=(0, 6))
        self.ent_br_title.bind("<FocusOut>", lambda e: self._apply_branch_id_title())
        self.ent_br_title.bind("<Return>", lambda e: self._apply_branch_id_title())

        # 본문
        body_frame = ttk.LabelFrame(edit_tab, text="본문(빈 줄로 문단 구분)", padding=6)
        body_frame.grid(row=4, column=0, columnspan=2, sticky="nsew")
        body_frame.rowconfigure(0, weight=1)
        body_frame.columnconfigure(0, weight=1)

        self.txt_body = tk.Text(body_frame, wrap="word", undo=True, height=20,
                                font=("Malgun Gothic", 12) if sys.platform.startswith("win") else ("Noto Sans CJK KR",
                                                                                                   12))
        self.txt_body.grid(row=0, column=0, sticky="nsew")
        scr = ttk.Scrollbar(body_frame, orient="vertical", command=self.txt_body.yview)
        scr.grid(row=0, column=1, sticky="ns")
        self.txt_body.configure(yscrollcommand=scr.set)
        self.txt_body.bind("<<Modified>>", self._on_body_modified)

        # 선택지 편집
        choices_frame = ttk.LabelFrame(edit_tab, text="선택지(버튼)", padding=6)
        choices_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        choices_frame.columnconfigure(0, weight=1)

        self.tree_choices = ttk.Treeview(choices_frame, columns=("text", "target"), show="headings", height=6)
        self.tree_choices.heading("text", text="버튼 문구")
        self.tree_choices.heading("target", text="타깃 분기 ID")
        self.tree_choices.column("text", width=400, anchor="w")
        self.tree_choices.column("target", width=160, anchor="w")
        self.tree_choices.grid(row=0, column=0, sticky="ew")

        ch_btns = ttk.Frame(choices_frame)
        ch_btns.grid(row=0, column=1, sticky="ns")
        ttk.Button(ch_btns, text="추가", command=self._add_choice).grid(row=0, column=0, pady=(0, 4))
        ttk.Button(ch_btns, text="편집", command=self._edit_choice).grid(row=1, column=0, pady=4)
        ttk.Button(ch_btns, text="삭제", command=self._delete_choice).grid(row=2, column=0, pady=4)
        ttk.Button(ch_btns, text="위로", command=lambda: self._reorder_choice(-1)).grid(row=3, column=0, pady=4)
        ttk.Button(ch_btns, text="아래로", command=lambda: self._reorder_choice(1)).grid(row=4, column=0, pady=4)

        # 미리보기 탭
        preview_tab = ttk.Frame(right, padding=8)
        right.add(preview_tab, text="생성 미리보기(.bnov)")
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
        ttk.Button(left_btns, text="유효성 검사", command=self._validate_story).pack(side="left")
        ttk.Button(left_btns, text="무한 루프 분석", command=self._analyze_infinite_loops).pack(side="left", padx=(6, 0))
        # 오른쪽: 저장/미리보기
        right_btns = ttk.Frame(bottom)
        right_btns.pack(side="right")
        ttk.Button(right_btns, text="저장", command=self._save_file).pack(side="right")
        ttk.Button(right_btns, text="미리보기 반영", command=self._apply_preview_to_model).pack(side="right", padx=(0, 6))
        ttk.Button(right_btns, text="미리보기 갱신", command=self._update_preview).pack(side="right", padx=(0, 6))
        ttk.Button(right_btns, text="미리보기 실행", command=self._run_preview).pack(side="right", padx=(0, 6))

        root.pack(fill="both", expand=True)

    # ---------- 핸들러 ----------
    def _on_title_changed(self):
        self.story.title = self.ent_title.get().strip() or "Untitled"
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
            "미리보기 반영",
            "미리보기에서 수정된 내용이 반영되지 않았습니다. 반영하시겠습니까?",
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
        self.ent_ch_title.delete(0, tk.END)
        self.ent_ch_title.insert(0, ch.title)
        self._refresh_branch_list()
        first = next(iter(ch.branches.keys()), None)
        if first:
            self._load_branch_to_form(first)

    def _load_branch_to_form(self, bid: str):
        self.current_branch_id = bid
        br = self.story.branches[bid]
        self.ent_br_id.delete(0, tk.END)
        self.ent_br_id.insert(0, br.branch_id)
        self.ent_br_title.delete(0, tk.END)
        self.ent_br_title.insert(0, br.title)

        self.txt_body.config(state="normal")
        self.txt_body.delete("1.0", tk.END)
        if br.paragraphs:
            self.txt_body.insert(tk.END, "\n\n".join(br.paragraphs))
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
        new_title = self.ent_ch_title.get().strip()
        if not new_id:
            messagebox.showerror("오류", "챕터 ID는 비울 수 없습니다.")
            self.ent_ch_id.focus_set()
            return
        cur_id = self.current_chapter_id
        if new_id != cur_id:
            if new_id in self.story.chapters:
                messagebox.showerror("오류", f"이미 존재하는 챕터 ID입니다: {new_id}")
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
        new_title = self.ent_br_title.get().strip()
        if not new_id:
            messagebox.showerror("오류", "분기 ID는 비울 수 없습니다.")
            self.ent_br_id.focus_set()
            return
        cur_id = self.current_branch_id
        if new_id != cur_id:
            if new_id in self.story.branches:
                messagebox.showerror("오류", f"이미 존재하는 분기 ID입니다: {new_id}")
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
            messagebox.showwarning("경고", "최소 한 개의 챕터는 필요합니다.")
            return
        cid = self.current_chapter_id
        ch = self.story.chapters[cid]
        if messagebox.askyesno("삭제 확인", f"챕터 '{cid}'를 삭제하시겠습니까?"):
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
            messagebox.showwarning("경고", "챕터에는 최소 한 개의 분기가 필요합니다.")
            return
        bid = self.current_branch_id
        if messagebox.askyesno("삭제 확인", f"분기 '{bid}'를 삭제하시겠습니까?"):
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
                messagebox.showerror("오류", "이미 존재하는 변수명입니다.")
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
                messagebox.showerror("오류", "이미 존재하는 변수명입니다.")
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
        if messagebox.askyesno("삭제 확인", f"변수 '{name}'를 삭제하시겠습니까?"):
            self.story.variables.pop(name, None)
            self._refresh_variable_list()
            self._set_dirty(True)
            self._update_preview()

    def _add_choice(self):
        if self.current_branch_id is None:
            return
        ids = list(self.story.branches.keys())
        vars = self._collect_variables()
        dlg = ChoiceEditor(self, "선택지 추가", None, ids, vars)
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
        dlg = ChoiceEditor(self, "선택지 편집", cur, ids, vars)
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
        win.title("찾기/변경")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._close_find_window)
        self.find_win = win

        win.columnconfigure(1, weight=1)

        scope_frame = ttk.LabelFrame(win, text="찾기 범위", padding=6)
        scope_frame.grid(row=0, column=0, columnspan=2, sticky="w")
        self.find_scope = tk.StringVar(value="branch")
        ttk.Radiobutton(scope_frame, text="이 분기", variable=self.find_scope, value="branch").pack(side="left")
        ttk.Radiobutton(scope_frame, text="프로젝트 전체", variable=self.find_scope, value="project").pack(side="left", padx=10)

        ttk.Label(win, text="찾을 문자열").grid(row=1, column=0, sticky="w", pady=(10,0))
        self.ent_find = ttk.Entry(win)
        self.ent_find.grid(row=1, column=1, sticky="ew", pady=(10,0))

        ttk.Label(win, text="바꿀 문자열").grid(row=2, column=0, sticky="w", pady=(6,0))
        self.ent_replace = ttk.Entry(win)
        self.ent_replace.grid(row=2, column=1, sticky="ew", pady=(6,0))

        nav = ttk.Frame(win)
        nav.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(nav, text="이전", command=lambda: self._find_step(-1)).pack(side="left")
        ttk.Button(nav, text="다음", command=lambda: self._find_step(1)).pack(side="left", padx=5)
        ttk.Button(nav, text="바꾸기", command=self._replace_current).pack(side="left", padx=5)

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
            messagebox.showinfo("찾기", "결과가 없습니다.")
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
            messagebox.showerror("파싱 오류", str(e))
            return False
        self.story = story
        self.current_branch_id = story.start_id
        br = self.story.get_branch(self.current_branch_id) if self.current_branch_id else None
        self.current_chapter_id = (
            br.chapter_id if br else (next(iter(self.story.chapters.keys())) if self.story.chapters else None)
        )
        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, self.story.title)
        self._refresh_chapter_list()
        # 미리보기에서 변경된 메타데이터를 반영
        self._refresh_meta_panel()
        if self.current_chapter_id:
            self._load_chapter_to_form(self.current_chapter_id)
            if self.current_branch_id:
                self._load_branch_to_form(self.current_branch_id)
        else:
            self.txt_body.delete("1.0", tk.END)
            for i in self.tree_choices.get_children():
                self.tree_choices.delete(i)
        # 미리보기 텍스트의 수정 플래그 초기화
        self.txt_preview.edit_modified(False)
        self.preview_modified = False
        return True

    def _run_preview(self):
        """branching_novel.py의 실행기를 이용하여 현재 스토리를 실행한다."""
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()

        import copy
        from branching_novel import BranchingNovelApp

        preview_story = copy.deepcopy(self.story)
        file_path = self.current_file or "<preview>"
        app = BranchingNovelApp(preview_story, file_path)
        app.mainloop()

    def _validate_story(self):
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()
        errors = []
        warnings = []

        if not self.story.title.strip():
            errors.append("작품 제목이 비어 있습니다.")
        if not self.story.start_id or self.story.start_id not in self.story.branches:
            errors.append("시작 분기(@start)가 유효하지 않습니다.")

        ids = set(self.story.branches.keys())
        for bid, br in self.story.branches.items():
            if not br.branch_id.strip():
                errors.append(f"분기 ID가 비어 있습니다: 내부키={bid}")
            if br.branch_id != bid:
                errors.append(f"내부키와 분기 ID가 불일치합니다: {bid} != {br.branch_id}")
            for c in br.choices:
                if c.target_id not in ids:
                    warnings.append(f"[{bid}] 선택지 타깃 미존재: '{c.text}' -> {c.target_id}")

        for cid, ch in self.story.chapters.items():
            if not ch.branches:
                warnings.append(f"챕터 '{cid}'에 분기가 없습니다.")

        msg = []
        if errors:
            msg.append("오류:")
            msg.extend(f"- {e}" for e in errors)
        if warnings:
            if msg:
                msg.append("")
            msg.append("경고:")
            msg.extend(f"- {w}" for w in warnings)

        if not msg:
            messagebox.showinfo("유효성 검사", "문제 없음.")
        else:
            messagebox.showwarning("유효성 검사 결과", "\n".join(msg))

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
        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, self.story.title)
        self._refresh_chapter_list()
        self._load_chapter_to_form(ch_id)
        self._refresh_meta_panel()
        self._update_preview()
        self._set_dirty(False)

    def _open_file(self):
        if not self._confirm_discard_changes():
            return
        path = filedialog.askopenfilename(title="열기", filetypes=[("Branching Novel Files","*.bnov"),("All Files","*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            parser = StoryParser()
            story = parser.parse(text)
        except ParseError as e:
            messagebox.showerror("파싱 오류", str(e))
            return
        except Exception as e:
            messagebox.showerror("오류", f"파일을 열 수 없습니다:\n{e}")
            return

        self.story = story
        self.current_branch_id = story.start_id
        br = self.story.get_branch(self.current_branch_id) if self.current_branch_id else None
        self.current_chapter_id = br.chapter_id if br else (next(iter(self.story.chapters.keys())) if self.story.chapters else None)
        self.current_file = path

        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, self.story.title)
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
            messagebox.showerror("오류", f"저장 실패:\n{e}")
            return
        self._set_dirty(False)
        messagebox.showinfo("저장", "저장 완료.")

    def _save_file_as(self):
        if not self._apply_preview_to_model():
            return
        self._apply_body_to_model()
        path = filedialog.asksaveasfilename(
            title="다른 이름으로 저장",
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
            messagebox.showerror("오류", f"저장 실패:\n{e}")
            return
        self.current_file = path
        self._set_dirty(False)
        self.title(f"Branching Novel Editor - {os.path.basename(path)}")
        messagebox.showinfo("저장", "저장 완료.")

    def _exit_app(self):
        # 1) 미리보기에서 수정한 내용이 있으면 먼저 처리(반영 or 폐기)
        if not self._ensure_preview_applied():
            return

        # 2) 더티 플래그가 있으면 저장 여부 확인
        if self.dirty:
            res = messagebox.askyesnocancel("변경 내용", "저장하지 않은 변경사항이 있습니다. 저장하시겠습니까?")
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
        res = messagebox.askyesnocancel("변경 내용", "저장하지 않은 변경사항이 있습니다. 저장하시겠습니까?")
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
            messagebox.showerror("오류", "시작 분기(@start)가 유효하지 않습니다.")
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
                        verdict = "불확실(복잡식)"
                        cond_s = "(복잡식)"
                    else:
                        every = eval_atoms_over_interval(atoms, pst)
                        cond_s = " and ".join(f"{v} {op} {val}" for (v, op, val) in atoms) if atoms else "(조건 없음)"
                        if every is True:
                            verdict = "항상 열림"
                        else:
                            sat = refine_with_atoms(atoms, pst) is not None
                            verdict = "가능" if sat else "불가능"
                    items.append(f"{bid} → {ch.target_id} | {cond_s} | {verdict}")
            if not items: return "외부 탈출 경로 없음"
            if len(items) > max_list:
                return "\n".join(items[:max_list] + [f"... (+{len(items) - max_list}개 더 있음)"])
            return "\n".join(items)

        lines = []
        lines.append("무한 루프 진단 요약")
        lines.append("")
        lines.append(f"- 확정: {len(definite)}개, 증거로 확인: {len(witnessed)}개, 검토 필요(가능): {len(possible)}개")
        lines.append("")

        if definite:
            lines.append("[확정 무한 루프]  반드시 수정 필요")
            for i, comp in enumerate(definite, 1):
                lines.append(f"{i}. 루프 노드 {len(comp)}개")
                lines.append(f"   요약 경로: {nodes_summary(comp)}")
                lines.append("   탈출 가능성: 외부 탈출 경로 없음(모든 노드가 내부로 항상 이동)")
                lines.append("   조치: 외부로 나가는 선택지 추가, 또는 내부 선택지에 탈출 조건(예: 변수 감소+임계 가드) 부여")
                lines.append("")
        if witnessed:
            lines.append("[증거 경로로 확인된 무한 루프]  실제 실행으로 반복됨")
            for i, (comp, path) in enumerate(witnessed, 1):
                lines.append(f"{i}. 루프 노드 {len(comp)}개")
                lines.append(f"   요약 경로: {nodes_summary(comp)}")
                lines.append("   예시 실행 경로(일부):")
                for step in path[:12]:
                    src_bid, text, tgt_bid = step
                    lines.append(f"     {src_bid} --[{text}]--> {tgt_bid}")
                if len(path) > 12:
                    lines.append(f"     ... (+{len(path) - 12} 단계)")
                ex = exit_edges_summary(comp, max_list=2)
                lines.append("   외부 탈출 후보:")
                for ln in ex.split("\n"):
                    lines.append("     " + ln)
                lines.append("   조치: 위 탈출 후보의 조건을 충족시킬 기회가 실제로 오는지 확인. 필요 시 조건/액션 설계 조정")
                lines.append("")
        if possible:
            lines.append("[검토 필요(가능 무한 루프)]  구조상 순환, 탈출 경로는 있을 수 있음")
            for i, comp in enumerate(possible, 1):
                lines.append(f"{i}. 루프 노드 {len(comp)}개")
                lines.append(f"   요약 경로: {nodes_summary(comp)}")
                ex = exit_edges_summary(comp, max_list=3)
                lines.append("   외부 탈출 요약:")
                for ln in ex.split("\n"):
                    lines.append("     " + ln)
                lines.append("   조치: '항상 열림' 또는 '불확실' 엣지가 있다면 조건을 구체화. '가능'만 존재한다면 그 조건을 만족할 상태가 실제로 도달 가능한지 점검")
                lines.append("")

        lines.append("정의:")
        lines.append("- 확정: 각 노드에서 내부 이동이 항상 가능하고, 외부 탈출은 어떤 상태에서도 불가능")
        lines.append("- 증거: 실제 값으로 내부만 따라가 반복 도달 확인")
        lines.append("- 가능: 순환은 있으나 외부 탈출이 조건에 따라 열릴 수 있음")

        # 팝업 표시
        win = tk.Toplevel(self)
        win.title("무한 루프 분석")
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

        ttk.Button(win, text="닫기", command=win.destroy).pack(pady=6)


# ---------- 진입점 ----------

def main():
    app = ChapterEditor()
    app.mainloop()

if __name__ == "__main__":
    main()
