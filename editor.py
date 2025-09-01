#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Branching Novel Editor (GUI)
- 분기형 소설 문법을 직접 쓰지 않고 GUI로 작성하여 .bnov를 자동 생성
- 기능:
  * 작품 제목(@title), 시작 챕터(@start) 설정
  * 챕터(분기) 추가/삭제/편집: id, 제목, 본문
  * 챕터별 선택지(버튼) 추가/삭제/편집: 버튼 문구, 이동 타깃 챕터 id
  * 챕터 ID 변경 시 해당 ID를 타깃으로 하는 선택지 자동 수정
  * 파일 신규/열기/저장/다른 이름으로 저장
  * 현재 상태를 문법에 맞는 텍스트로 미리보기
  * 기존 포맷(.bnov) 불러오기(파싱)

문법 포맷(생성 결과):
  @title: 작품 제목
  @start: 시작챕터ID

  # chapter_id: Chapter Title
  본문 문단1

  본문 문단2

  * 버튼 문구 -> target_id
  * 버튼 문구2 -> target_id2

주의:
  - 챕터 id는 고유해야 함.
  - 선택지 타깃은 존재하지 않는 챕터를 가리킬 수도 있으나, 저장 전 유효성 경고 제공.
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
class Chapter:
    chapter_id: str
    title: str
    paragraphs: List[str] = field(default_factory=list)
    choices: List[Choice] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)

@dataclass
class Story:
    title: str = "Untitled"
    start_id: Optional[str] = None
    ending_text: str = "The End"
    chapters: Dict[str, Chapter] = field(default_factory=dict)
    variables: Dict[str, Union[int, float, bool]] = field(default_factory=dict)

    def chapter_ids(self) -> List[str]:
        return list(self.chapters.keys())

    def ensure_unique_id(self, base: str = "chapter") -> str:
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

    def serialize(self) -> str:
        lines = []
        # metadata
        lines.append(f"@title: {self.title}".rstrip())
        if self.start_id:
            lines.append(f"@start: {self.start_id}")
        lines.append(f"@ending: {self.ending_text}")
        # global variables
        for var in sorted(self.variables.keys()):
            val = self.variables[var]
            val_str = str(val).lower() if isinstance(val, bool) else val
            lines.append(f"! {var} = {val_str}")
        lines.append("")  # blank line

        # chapters in insertion order
        for cid, ch in self.chapters.items():
            header = f"# {ch.chapter_id}: {ch.title}" if ch.title else f"# {ch.chapter_id}"
            lines.append(header)
            # paragraphs
            for p in ch.paragraphs:
                lines.append(p.rstrip())
                lines.append("")  # blank line between paragraphs
            # remove trailing blank if any paragraph exists
            if len(ch.paragraphs) > 0 and len(lines) > 0 and lines[-1] == "":
                pass
            # actions
            op_map = {
                "add": "+=",
                "sub": "-=",
                "mul": "*=",
                "div": "/=",
                "floordiv": "//=",
                "mod": "%=",
                "pow": "**=",
            }
            for act in ch.actions:
                if act.op == "set":
                    lines.append(f"! {act.var} = {act.value}")
                else:
                    sym = op_map.get(act.op)
                    if sym:
                        lines.append(f"! {act.var} {sym} {act.value}")
            # choices
            for c in ch.choices:
                if c.condition:
                    lines.append(f"* [{c.condition}] {c.text} -> {c.target_id}")
                else:
                    lines.append(f"* {c.text} -> {c.target_id}")
            lines.append("")  # blank line after chapter
        # trim trailing blanks
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

# ---------- 파서 (열기용) ----------

class ParseError(Exception):
    pass

class StoryParser:
    def parse(self, text: str) -> Story:
        lines = text.splitlines()
        story = Story()
        current: Optional[Chapter] = None
        buffer: List[str] = []

        # metadata first pass
        for raw in lines:
            s = raw.strip()
            if s.startswith("@title:"):
                story.title = s[len("@title:"):].strip() or "Untitled"
            elif s.startswith("@start:"):
                story.start_id = s[len("@start:"):].strip() or None
            elif s.startswith("@ending:"):
                story.ending_text = s[len("@ending:"):].strip() or "The End"

        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip("\n")
            s = line.strip()
            i += 1

            if s.startswith("#"):
                if current is not None and buffer:
                    current.paragraphs.extend(self._flush_paragraphs(buffer))
                    buffer.clear()
                current = self._parse_header(s)
                if current.chapter_id in story.chapters:
                    raise ParseError(f"Duplicate chapter id: {current.chapter_id}")
                story.chapters[current.chapter_id] = current
                continue

            if s == "":
                if current is not None and buffer:
                    current.paragraphs.extend(self._flush_paragraphs(buffer))
                    buffer.clear()
                continue

            if s.startswith("!"):
                act = self._parse_action(s)
                if current is None:
                    if act.op != "set":
                        raise ParseError("Action outside of a chapter.")
                    story.variables[act.var] = act.value
                else:
                    current.actions.append(act)
                continue

            if s.startswith("* "):
                if current is None:
                    raise ParseError("Choice outside of a chapter.")
                ch = self._parse_choice(s)
                current.choices.append(ch)
                continue

            if current is None:
                raise ParseError("Narrative outside of a chapter.")
            buffer.append(line)

        if current is not None and buffer:
            current.paragraphs.extend(self._flush_paragraphs(buffer))
            buffer.clear()

        if story.start_id is None:
            # auto-pick first chapter if any
            if story.chapters:
                story.start_id = next(iter(story.chapters.keys()))
            else:
                raise ParseError("No chapters.")
        return story

    def _flush_paragraphs(self, buf: List[str]) -> List[str]:
        if not buf:
            return []
        paragraphs = []
        cur = []
        for ln in buf:
            if ln.strip() == "":
                if cur:
                    paragraphs.append("\n".join(cur).strip())
                    cur = []
            else:
                cur.append(ln)
        if cur:
            paragraphs.append("\n".join(cur).strip())
        return paragraphs

    def _parse_header(self, s: str) -> Chapter:
        content = s.lstrip("#").strip()
        if ":" in content:
            cid, title = content.split(":", 1)
            return Chapter(chapter_id=cid.strip(), title=title.strip())
        return Chapter(chapter_id=content.strip(), title=content.strip())

    def _parse_choice(self, s: str) -> Choice:
        body = s[2:].strip()
        if "->" not in body:
            raise ParseError("Choice must contain '->'.")
        left, right = body.split("->", 1)
        left = left.strip()
        condition: Optional[str] = None
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
            raise ParseError("Empty choice text or target.")
        return Choice(text=text, target_id=target, condition=condition)

    def _parse_action(self, s: str) -> Action:
        content = s[1:].strip()
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
    def __init__(self, master):
        super().__init__(master)
        self.title("변수 추가")
        self.resizable(False, False)
        self.result_ok = False
        self.var_name: str = ""
        self.value: Union[int, float, bool] = 0

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="변수명").grid(row=0, column=0, sticky="w")
        self.ent_name = ttk.Entry(frm, width=20)
        self.ent_name.grid(row=1, column=0, sticky="ew", pady=(0,8))

        ttk.Label(frm, text="초기값").grid(row=0, column=1, sticky="w", padx=(8,0))
        self.ent_val = ttk.Entry(frm, width=10)
        self.ent_val.grid(row=1, column=1, sticky="ew", padx=(8,0))

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
            editor._update_preview()

    def _ok(self):
        self.condition_str = " and ".join(f"{v} {op} {val}" for v, op, val in self.conditions)
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()


class ChoiceEditor(tk.Toplevel):
    def __init__(self, master, title: str, choice: Optional[Choice], chapter_ids: List[str], variables: List[str]):
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

        ttk.Label(frm, text="이동 타깃 챕터 ID").grid(row=2, column=0, sticky="w")
        self.cmb_target = ttk.Combobox(frm, values=chapter_ids, state="readonly", width=30)
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
            if chapter_ids:
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
            messagebox.showerror("오류", "이동 타깃 챕터 ID를 선택하세요.")
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
        # 초기 챕터 하나 생성
        init_id = self.story.ensure_unique_id("intro")
        self.story.chapters[init_id] = Chapter(chapter_id=init_id, title="Introduction", paragraphs=[], choices=[])
        self.story.start_id = init_id

        self.current_chapter_id: Optional[str] = init_id
        self.current_file: Optional[str] = None
        self.dirty: bool = False

        self._build_menu()
        self._build_ui()
        self._refresh_chapter_list()
        self._load_chapter_to_form(init_id)
        self._refresh_meta_panel()
        self._update_preview()

        # 찾기/변경 상태
        self.find_results: List[Tuple[str, int]] = []
        self.find_index: int = -1
        self._last_find_text: str = ""
        self._last_find_scope: str = "chapter"

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
        root.pack(fill="both", expand=True)

        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsw", padx=(0,8))
        left.rowconfigure(2, weight=1)

        # 작품 메타
        meta = ttk.LabelFrame(left, text="작품 정보", padding=8)
        meta.grid(row=0, column=0, sticky="ew")
        meta.columnconfigure(1, weight=1)

        ttk.Label(meta, text="제목(@title)").grid(row=0, column=0, sticky="w")
        self.ent_title = ttk.Entry(meta, width=30)
        self.ent_title.grid(row=0, column=1, sticky="ew", pady=(0,6))
        self.ent_title.insert(0, self.story.title)
        self.ent_title.bind("<KeyRelease>", lambda e: self._on_title_changed())

        ttk.Label(meta, text="시작 챕터(@start)").grid(row=1, column=0, sticky="w")
        self.cmb_start = ttk.Combobox(meta, values=[], state="readonly")
        self.cmb_start.grid(row=1, column=1, sticky="ew")
        self.cmb_start.bind("<<ComboboxSelected>>", lambda e: self._on_start_changed())

        ttk.Label(meta, text="엔딩 문구(@ending)").grid(row=2, column=0, sticky="w")
        self.ent_end = ttk.Entry(meta, width=30)
        self.ent_end.grid(row=2, column=1, sticky="ew")
        self.ent_end.insert(0, self.story.ending_text)
        self.ent_end.bind("<KeyRelease>", lambda e: self._on_ending_changed())

        # 챕터 목록
        chap_frame = ttk.LabelFrame(left, text="챕터 목록", padding=8)
        chap_frame.grid(row=2, column=0, sticky="nsew", pady=(8,0))
        chap_frame.rowconfigure(1, weight=1)
        chap_frame.columnconfigure(0, weight=1)

        self.lst_chapters = tk.Listbox(chap_frame, height=20, exportselection=False)
        self.lst_chapters.grid(row=1, column=0, sticky="nsew")
        self.lst_chapters.bind("<<ListboxSelect>>", lambda e: self._on_select_chapter())
        self.lst_chapters.bind("<Double-Button-1>", lambda e: self._on_select_chapter())

        btns = ttk.Frame(chap_frame)
        btns.grid(row=0, column=0, sticky="ew", pady=(0,6))
        ttk.Button(btns, text="추가", command=self._add_chapter).pack(side="left")
        ttk.Button(btns, text="삭제", command=self._delete_current_chapter).pack(side="left", padx=(6,0))
        ttk.Button(btns, text="위로", command=lambda: self._reorder_chapter(-1)).pack(side="left", padx=(6,0))
        ttk.Button(btns, text="아래로", command=lambda: self._reorder_chapter(1)).pack(side="left", padx=(6,0))

        # 우측 편집/미리보기 영역
        right = ttk.Notebook(root)
        right.grid(row=0, column=1, sticky="nsew")
        self.nb_right = right

        # 챕터 편집 탭
        edit_tab = ttk.Frame(right, padding=8)
        right.add(edit_tab, text="챕터 편집")

        edit_tab.columnconfigure(1, weight=1)
        edit_tab.rowconfigure(3, weight=1)

        ttk.Label(edit_tab, text="챕터 ID").grid(row=0, column=0, sticky="w")
        self.ent_ch_id = ttk.Entry(edit_tab)
        self.ent_ch_id.grid(row=0, column=1, sticky="ew", pady=(0,6))
        self.ent_ch_id.bind("<FocusOut>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_id.bind("<Return>", lambda e: self._apply_chapter_id_title())

        ttk.Label(edit_tab, text="챕터 제목").grid(row=1, column=0, sticky="w")
        self.ent_ch_title = ttk.Entry(edit_tab)
        self.ent_ch_title.grid(row=1, column=1, sticky="ew", pady=(0,6))
        self.ent_ch_title.bind("<FocusOut>", lambda e: self._apply_chapter_id_title())
        self.ent_ch_title.bind("<Return>", lambda e: self._apply_chapter_id_title())

        # 본문
        body_frame = ttk.LabelFrame(edit_tab, text="본문(빈 줄로 문단 구분)", padding=6)
        body_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        body_frame.rowconfigure(0, weight=1)
        body_frame.columnconfigure(0, weight=1)

        self.txt_body = tk.Text(body_frame, wrap="word", undo=True, height=20,
                                font=("Malgun Gothic", 12) if sys.platform.startswith("win") else ("Noto Sans CJK KR", 12))
        self.txt_body.grid(row=0, column=0, sticky="nsew")
        scr = ttk.Scrollbar(body_frame, orient="vertical", command=self.txt_body.yview)
        scr.grid(row=0, column=1, sticky="ns")
        self.txt_body.configure(yscrollcommand=scr.set)
        self.txt_body.bind("<<Modified>>", self._on_body_modified)

        # 선택지 편집
        choices_frame = ttk.LabelFrame(edit_tab, text="선택지(버튼)", padding=6)
        choices_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8,0))
        choices_frame.columnconfigure(0, weight=1)

        self.tree_choices = ttk.Treeview(choices_frame, columns=("text", "target"), show="headings", height=6)
        self.tree_choices.heading("text", text="버튼 문구")
        self.tree_choices.heading("target", text="타깃 챕터 ID")
        self.tree_choices.column("text", width=400, anchor="w")
        self.tree_choices.column("target", width=160, anchor="w")
        self.tree_choices.grid(row=0, column=0, sticky="ew")

        ch_btns = ttk.Frame(choices_frame)
        ch_btns.grid(row=0, column=1, sticky="ns")
        ttk.Button(ch_btns, text="추가", command=self._add_choice).grid(row=0, column=0, pady=(0,4))
        ttk.Button(ch_btns, text="편집", command=self._edit_choice).grid(row=1, column=0, pady=4)
        ttk.Button(ch_btns, text="삭제", command=self._delete_choice).grid(row=2, column=0, pady=4)
        ttk.Button(ch_btns, text="위로", command=lambda: self._reorder_choice(-1)).grid(row=3, column=0, pady=4)
        ttk.Button(ch_btns, text="아래로", command=lambda: self._reorder_choice(1)).grid(row=4, column=0, pady=4)

        # 미리보기 탭
        preview_tab = ttk.Frame(right, padding=8)
        right.add(preview_tab, text="생성 미리보기(.bnov)")
        preview_tab.rowconfigure(0, weight=1)
        preview_tab.columnconfigure(0, weight=1)

        self.txt_preview = tk.Text(preview_tab, wrap="none", state="disabled",
                                   font=("Consolas", 11) if sys.platform.startswith("win") else ("Menlo", 11))
        self.txt_preview.grid(row=0, column=0, sticky="nsew")
        pvx = ttk.Scrollbar(preview_tab, orient="horizontal", command=self.txt_preview.xview)
        pvy = ttk.Scrollbar(preview_tab, orient="vertical", command=self.txt_preview.yview)
        pvx.grid(row=1, column=0, sticky="ew")
        pvy.grid(row=0, column=1, sticky="ns")
        self.txt_preview.configure(xscrollcommand=pvx.set, yscrollcommand=pvy.set)

        # 찾기/변경은 새 창에서 열림
        self.find_win = None

        # 하단 버튼 바
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(bottom, text="유효성 검사", command=self._validate_story).pack(side="left")
        ttk.Button(bottom, text="저장", command=self._save_file).pack(side="right")
        ttk.Button(bottom, text="미리보기 갱신", command=self._update_preview).pack(side="right", padx=(0,6))
        ttk.Button(bottom, text="미리보기 실행", command=self._run_preview).pack(side="right", padx=(0,6))

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
            self._apply_body_to_model()  # 기존 챕터 본문 반영
            self._load_chapter_to_form(cid)

    def _on_body_modified(self, evt):
        # Text의 Modified 플래그를 수동 리셋
        if self.txt_body.edit_modified():
            self.txt_body.edit_modified(False)
            self._set_dirty(True)
            self._apply_body_to_model()
            self._update_preview()

    # ---------- 상호작용 ----------
    def _load_chapter_to_form(self, cid: str):
        self.current_chapter_id = cid
        ch = self.story.chapters[cid]
        self.ent_ch_id.delete(0, tk.END)
        self.ent_ch_id.insert(0, ch.chapter_id)
        self.ent_ch_title.delete(0, tk.END)
        self.ent_ch_title.insert(0, ch.title)

        self.txt_body.config(state="normal")
        self.txt_body.delete("1.0", tk.END)
        # 문단을 빈 줄로 결합하여 편집
        if ch.paragraphs:
            joined = "\n\n".join(ch.paragraphs)
            self.txt_body.insert(tk.END, joined)
        self.txt_body.edit_modified(False)

        for i in self.tree_choices.get_children():
            self.tree_choices.delete(i)
        for c in ch.choices:
            self.tree_choices.insert("", tk.END, values=(c.text, c.target_id))

        self._refresh_meta_panel()
        self._update_preview()

    def _apply_body_to_model(self):
        if self.current_chapter_id is None:
            return
        ch = self.story.chapters[self.current_chapter_id]
        raw = self.txt_body.get("1.0", tk.END).rstrip("\n")
        paras = [p.strip() for p in raw.split("\n\n")]
        paras = [p for p in paras if p != ""]
        ch.paragraphs = paras

    def _apply_chapter_id_title(self):
        if self.current_chapter_id is None:
            return
        new_id = self.ent_ch_id.get().strip()
        new_title = self.ent_ch_title.get().strip()
        if not new_id:
            messagebox.showerror("오류", "챕터 ID는 비울 수 없습니다.")
            self.ent_ch_id.focus_set()
            return

        # ID 변경 처리
        cur_id = self.current_chapter_id
        reload_needed = False
        if new_id != cur_id:
            if new_id in self.story.chapters:
                messagebox.showerror("오류", f"이미 존재하는 챕터 ID입니다: {new_id}")
                self.ent_ch_id.delete(0, tk.END)
                self.ent_ch_id.insert(0, cur_id)
                return
            # 키 교체
            ch_obj = self.story.chapters.pop(cur_id)
            ch_obj.chapter_id = new_id
            self.story.chapters[new_id] = ch_obj
            self.current_chapter_id = new_id

            # 다른 챕터들의 선택지 타깃에서 기존 ID를 사용 중인 경우 모두 새 ID로 변경
            for ch in self.story.chapters.values():
                for c in ch.choices:
                    if c.target_id == cur_id:
                        c.target_id = new_id

            # 시작 챕터가 기존 ID를 가리키면 갱신
            if self.story.start_id == cur_id:
                self.story.start_id = new_id

            reload_needed = True

        # 제목 반영
        self.story.chapters[new_id].title = new_title

        # 리스트/폼 갱신
        self._refresh_chapter_list()
        if reload_needed:
            # 현재 챕터 폼을 다시 로드하여 변경된 선택지 타깃 반영
            self._load_chapter_to_form(new_id)

        self._set_dirty(True)
        self._update_preview()

    def _refresh_chapter_list(self):
        self.lst_chapters.delete(0, tk.END)
        for cid, ch in self.story.chapters.items():
            self.lst_chapters.insert(tk.END, f"{cid}  |  {ch.title}")
        # 현재 선택 유지
        if self.current_chapter_id and self.current_chapter_id in self.story.chapters:
            idx = list(self.story.chapters.keys()).index(self.current_chapter_id)
            self.lst_chapters.selection_clear(0, tk.END)
            self.lst_chapters.selection_set(idx)
            self.lst_chapters.see(idx)
        self._refresh_meta_panel()

    def _refresh_meta_panel(self):
        ids = list(self.story.chapters.keys())
        self.cmb_start["values"] = ids
        if self.story.start_id in ids:
            self.cmb_start.set(self.story.start_id)
        elif ids:
            self.cmb_start.set(ids[0])
            self.story.start_id = ids[0]
        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, self.story.ending_text)

    def _add_chapter(self):
        # 현재 변경사항 반영
        self._apply_body_to_model()
        base = "chapter"
        new_id = self.story.ensure_unique_id(base)
        self.story.chapters[new_id] = Chapter(chapter_id=new_id, title="New Chapter", paragraphs=[], choices=[])
        self.current_chapter_id = new_id
        self._refresh_chapter_list()
        self._load_chapter_to_form(new_id)
        self._set_dirty(True)

    def _delete_current_chapter(self):
        if self.current_chapter_id is None:
            return
        if len(self.story.chapters) <= 1:
            messagebox.showwarning("경고", "최소 한 개의 챕터는 필요합니다.")
            return
        cid = self.current_chapter_id
        if messagebox.askyesno("삭제 확인", f"챕터 '{cid}'를 삭제하시겠습니까?"):
            # 시작 챕터였을 경우 다른 챕터로 옮김
            keys = list(self.story.chapters.keys())
            next_id = None
            if len(keys) > 1:
                for k in keys:
                    if k != cid:
                        next_id = k
                        break
            self.story.chapters.pop(cid)
            # 참조 정리는 하지 않음. 유효성 검사 시 경고됨.
            if self.story.start_id == cid:
                self.story.start_id = next_id
            self.current_chapter_id = next_id
            self._refresh_chapter_list()
            if next_id:
                self._load_chapter_to_form(next_id)
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

    def _collect_variables(self) -> List[str]:
        vars_set = set(self.story.variables.keys())
        for ch in self.story.chapters.values():
            for act in ch.actions:
                vars_set.add(act.var)
        return sorted(vars_set)

    def _add_choice(self):
        if self.current_chapter_id is None:
            return
        ids = list(self.story.chapters.keys())
        vars = self._collect_variables()
        dlg = ChoiceEditor(self, "선택지 추가", None, ids, vars)
        if dlg.result_ok and dlg.choice:
            ch = self.story.chapters[self.current_chapter_id]
            ch.choices.append(dlg.choice)
            self.tree_choices.insert("", tk.END, values=(dlg.choice.text, dlg.choice.target_id))
            self._set_dirty(True)
            self._update_preview()

    def _edit_choice(self):
        sel = self.tree_choices.selection()
        if not sel:
            return
        idx = self.tree_choices.index(sel[0])
        ch = self.story.chapters[self.current_chapter_id]
        cur = ch.choices[idx]
        ids = list(self.story.chapters.keys())
        vars = self._collect_variables()
        dlg = ChoiceEditor(self, "선택지 편집", cur, ids, vars)
        if dlg.result_ok and dlg.choice:
            ch.choices[idx] = dlg.choice
            self.tree_choices.item(sel[0], values=(dlg.choice.text, dlg.choice.target_id))
            self._set_dirty(True)
            self._update_preview()

    def _delete_choice(self):
        sel = self.tree_choices.selection()
        if not sel:
            return
        idx = self.tree_choices.index(sel[0])
        ch = self.story.chapters[self.current_chapter_id]
        ch.choices.pop(idx)
        self.tree_choices.delete(sel[0])
        self._set_dirty(True)
        self._update_preview()

    def _reorder_choice(self, delta: int):
        sel = self.tree_choices.selection()
        if not sel:
            return
        cur_idx = self.tree_choices.index(sel[0])
        new_idx = cur_idx + delta
        ch = self.story.chapters[self.current_chapter_id]
        if new_idx < 0 or new_idx >= len(ch.choices):
            return
        ch.choices[cur_idx], ch.choices[new_idx] = ch.choices[new_idx], ch.choices[cur_idx]
        # 트리뷰 갱신
        for i in self.tree_choices.get_children():
            self.tree_choices.delete(i)
        for c in ch.choices:
            self.tree_choices.insert("", tk.END, values=(c.text, c.target_id))
        # 선택 재설정
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
        self.find_scope = tk.StringVar(value="chapter")
        ttk.Radiobutton(scope_frame, text="이 분기", variable=self.find_scope, value="chapter").pack(side="left")
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
        if scope == "chapter" and self.current_chapter_id:
            ch = self.story.chapters[self.current_chapter_id]
            text = "\n\n".join(ch.paragraphs)
            idx = text.find(query)
            while idx != -1:
                results.append((self.current_chapter_id, idx))
                idx = text.find(query, idx + len(query))
        else:
            for cid, ch in self.story.chapters.items():
                text = "\n\n".join(ch.paragraphs)
                idx = text.find(query)
                while idx != -1:
                    results.append((cid, idx))
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
        cid, pos = self.find_results[self.find_index]
        if cid != self.current_chapter_id:
            self._load_chapter_to_form(cid)
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
        cid, pos = self.find_results[self.find_index]
        if cid != self.current_chapter_id:
            self._load_chapter_to_form(cid)
        start = f"1.0+{pos}c"
        end = f"{start}+{len(query)}c"
        self.txt_body.delete(start, end)
        self.txt_body.insert(start, replacement)
        self._apply_body_to_model()
        self._build_find_results(query, self.find_scope.get())
        self._find_step(1)

    def _update_preview(self):
        self._apply_body_to_model()
        txt = self.story.serialize()
        self.txt_preview.config(state="normal")
        self.txt_preview.delete("1.0", tk.END)
        self.txt_preview.insert(tk.END, txt)
        self.txt_preview.config(state="disabled")

    def _run_preview(self):
        """현재 스토리를 간단히 실행해 볼 수 있는 팝업을 띄운다."""
        self._apply_body_to_model()

        state: Dict[str, Union[int, float, bool]] = {}
        current: Optional[Chapter] = None

        def apply_actions(ch: Chapter):
            for act in ch.actions:
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

        def eval_cond(cond: str) -> bool:
            expr = re.sub(r"\btrue\b", "True", cond, flags=re.IGNORECASE)
            expr = re.sub(r"\bfalse\b", "False", expr, flags=re.IGNORECASE)

            class Env(dict):
                def __missing__(self, key):
                    return 0

            env = Env()
            env.update(state)
            try:
                return bool(eval(expr, {"__builtins__": None}, env))
            except Exception:
                return False

        win = tk.Toplevel(self)
        win.title("Runtime Preview")
        win.geometry("600x400")

        text = tk.Text(win, wrap="word", state="disabled")
        text.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=8, pady=(0,8))

        def show(cid: str):
            nonlocal current
            ch = self.story.chapters.get(cid)
            if not ch:
                messagebox.showerror("오류", f"챕터를 찾을 수 없습니다: {cid}", parent=win)
                win.destroy()
                return
            current = ch
            apply_actions(ch)
            text.config(state="normal")
            text.delete("1.0", tk.END)
            for p in ch.paragraphs:
                text.insert(tk.END, p + "\n\n")
            text.config(state="disabled")

            for child in btn_frame.winfo_children():
                child.destroy()

            display = []
            for c in ch.choices:
                ok = True
                if c.condition:
                    ok = eval_cond(c.condition)
                if ok:
                    display.append(c)

            if display:
                for c in display:
                    ttk.Button(btn_frame, text=c.text, command=lambda c=c: choose(c)).pack(fill="x", pady=2)
            else:
                ttk.Button(btn_frame, text="닫기", command=win.destroy).pack(pady=2)

        def choose(choice: Choice):
            show(choice.target_id)

        start = self.story.start_id or next(iter(self.story.chapters.keys()), None)
        if not start:
            messagebox.showerror("오류", "챕터가 없습니다.", parent=win)
            win.destroy()
            return
        show(start)

    def _validate_story(self):
        errors = []
        warnings = []

        if not self.story.title.strip():
            errors.append("작품 제목이 비어 있습니다.")
        if not self.story.start_id or self.story.start_id not in self.story.chapters:
            errors.append("시작 챕터(@start)가 유효하지 않습니다.")

        ids = set(self.story.chapters.keys())
        for cid, ch in self.story.chapters.items():
            if not ch.chapter_id.strip():
                errors.append(f"챕터 ID가 비어 있습니다: 내부키={cid}")
            if ch.chapter_id != cid:
                errors.append(f"내부키와 챕터 ID가 불일치합니다: {cid} != {ch.chapter_id}")
            # 선택지 타깃 유효성
            for c in ch.choices:
                if c.target_id not in ids:
                    warnings.append(f"[{cid}] 선택지 타깃 미존재: '{c.text}' -> {c.target_id}")

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
        intro_id = self.story.ensure_unique_id("intro")
        self.story.chapters[intro_id] = Chapter(chapter_id=intro_id, title="Introduction", paragraphs=[], choices=[])
        self.story.start_id = intro_id
        self.current_chapter_id = intro_id
        self.current_file = None
        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, self.story.title)
        self._refresh_chapter_list()
        self._load_chapter_to_form(intro_id)
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
        # dict 유지: 파서는 본문 순서대로 chapters 삽입하므로 그 순서 유지
        self.current_chapter_id = story.start_id
        self.current_file = path

        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, self.story.title)
        self._refresh_chapter_list()
        if self.current_chapter_id is None:
            self.current_chapter_id = next(iter(self.story.chapters.keys()))
        self._load_chapter_to_form(self.current_chapter_id)
        self._refresh_meta_panel()
        self._update_preview()
        self._set_dirty(False)
        self.title(f"Branching Novel Editor - {os.path.basename(path)}")

    def _save_file(self):
        if self.current_file is None:
            return self._save_file_as()
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
        if not self._confirm_discard_changes():
            return
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

# ---------- 진입점 ----------

def main():
    app = ChapterEditor()
    app.mainloop()

if __name__ == "__main__":
    main()
