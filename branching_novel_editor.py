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
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

from i18n import tr, set_language, set_language_from_file, get_user_lang_file
from typing import Any, List, Dict, Optional, Callable, Iterable, Tuple, Union, Set
import copy

from auto_update import check_for_update
from story_parser import Choice, Action, Branch, Chapter, Story, ParseError, StoryParser
from branching_novel_app import BranchingNovelApp, VAR_PATTERN


APP_NAME = "Branching Novel Editor"
INSTALLER_NAME = "BranchingNovelEditor-Online-Setup.exe"
APP_ID = "667FEBC7-64DB-446E-97B5-E6886D5E4660"

COMPARISON_OPERATORS = ["==", "!=", ">", "<", ">=", "<="]
ASSIGNMENT_OPERATORS = ["=", "+=", "-=", "*=", "/=", "//=", "%=", "**="]


def highlight_variables(widget: tk.Text, get_vars: Callable[[], Iterable[str]]) -> None:
    """Highlight ``__var__`` placeholders referencing defined variables.

    The scanning logic mirrors ``BranchingNovelApp``'s variable interpolation
    so that the editor and runtime interpret placeholders identically.
    """
    try:
        widget.tag_remove("var", "1.0", tk.END)
        widget.tag_remove("comment", "1.0", tk.END)
    except tk.TclError:
        return

    text = widget.get("1.0", "end-1c")

    # 주석 처리: 일반/블록/줄 옆 주석 모두 회색으로 표시
    start = 0
    in_block = False
    for line in text.splitlines(True):
        stripped = line.strip()
        lstripped = line.lstrip()
        line_start = f"1.0+{start}c"
        line_end = f"1.0+{start + len(line)}c"

        if in_block:
            widget.tag_add("comment", line_start, line_end)
            if stripped == ";":
                in_block = False
            start += len(line)
            continue

        if stripped == ";":
            in_block = True
            widget.tag_add("comment", line_start, line_end)
        elif lstripped.startswith(";"):
            widget.tag_add("comment", line_start, line_end)
        else:
            idx = line.find(";")
            if idx != -1:
                widget.tag_add("comment", f"1.0+{start + idx}c", line_end)
        start += len(line)

    widget.tag_configure("comment", foreground="gray")

    vars_set = set(get_vars()) if get_vars else set()
    if vars_set:
        i = 0
        n = len(text)
        while i < n:
            j = text.find("__", i)
            if j == -1:
                break

            k = j + 2
            m = re.match(r"([A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)", text[k:])
            if not m:
                # 슬라이딩: '___var__'처럼 '__' 뒤에 식별자가 없으면 '_'만 소비
                i = j + 1
                continue

            name = m.group(1)
            k += m.end()

            if k + 2 <= n and text.startswith("__", k):
                if name in vars_set:
                    start_pos = f"1.0+{j}c"
                    end_pos = f"1.0+{k + 2}c"
                    widget.tag_add("var", start_pos, end_pos)
                # 정의 여부에 따라 소비 범위 결정
                i = k + 2 if name in vars_set else k
            else:
                # 슬라이딩: 닫힘 '__'가 없으면 '_'만 소비
                i = j + 1

        # 변수 스타일 설정
        base_font = tkfont.Font(font=widget.cget("font"))
        highlight_font = base_font.copy()
        highlight_font.configure(weight="bold")
        widget.tag_configure("var", foreground="navy", font=highlight_font)


# ---------- 에디터 GUI ----------


class UndoManager:
    """Simple undo/redo manager storing deep copies of editor state."""

    def __init__(self, get_state: Callable[[], Any], set_state: Callable[[Any], None]):
        self._get_state = get_state
        self._set_state = set_state
        self._undo_stack: List[Any] = [copy.deepcopy(self._get_state())]
        self._redo_stack: List[Any] = []

    def record(self) -> None:
        """Record a new state for undo."""
        self._undo_stack.append(copy.deepcopy(self._get_state()))
        self._redo_stack.clear()

    def undo(self) -> None:
        if len(self._undo_stack) <= 1:
            return
        state = self._undo_stack.pop()
        self._redo_stack.append(state)
        self._set_state(copy.deepcopy(self._undo_stack[-1]))

    def redo(self) -> None:
        if not self._redo_stack:
            return
        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        self._set_state(copy.deepcopy(state))

class ConditionRowDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        variables: List[str],
        initial: Optional[Tuple[str, str, str]],
        operators: List[str],
    ):
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
        self.cmb_op = ttk.Combobox(frm, values=operators, state="readonly", width=7)
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
            if operators:
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
    def __init__(self, master, name: str = "", value: Optional[Union[int, float, bool, str]] = None):
        super().__init__(master)
        self.title(tr("add_variable") if not name else tr("edit_variable"))
        self.resizable(False, False)
        self.result_ok = False
        self.var_name: str = name
        self.value: Union[int, float, bool, str] = value if value is not None else 0

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text=tr("variable_name")).grid(row=0, column=0, sticky="w")
        self.ent_name = ttk.Entry(frm, width=20, validate="key")
        vcmd = (self.register(self._validate_name), "%P")
        self.ent_name.configure(validatecommand=vcmd)
        self.ent_name.grid(row=1, column=0, sticky="ew", pady=(0,8))
        if name:
            self.ent_name.insert(0, name)

        ttk.Label(frm, text=tr("initial_value")).grid(row=0, column=1, sticky="w", padx=(8,0))
        self.ent_val = ttk.Entry(frm, width=10)
        self.ent_val.grid(row=1, column=1, sticky="ew", padx=(8,0))
        if value is not None:
            if isinstance(value, bool):
                self.ent_val.insert(0, str(value).lower())
            elif isinstance(value, str):
                self.ent_val.insert(0, f"{value!r}")
            else:
                self.ent_val.insert(0, str(value))

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
        if not re.fullmatch(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*", name):
            messagebox.showerror(tr("error"), tr("invalid_variable_name"))
            return
        if val_text.lower() == "true":
            val: Union[int, float, bool, str] = True
        elif val_text.lower() == "false":
            val = False
        elif (val_text.startswith('"') and val_text.endswith('"')) or (
            val_text.startswith("'") and val_text.endswith("'")
        ):
            try:
                val = ast.literal_eval(val_text)
            except Exception:
                messagebox.showerror(tr("error"), tr("invalid_initial_value"))
                return
        else:
            try:
                val = int(val_text)
            except ValueError:
                try:
                    val = float(val_text)
                except ValueError:
                    # Allow plain strings without quotes
                    val = val_text
        self.var_name = name
        self.value = val
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()

    def _validate_name(self, proposed: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_]*", proposed))


class ActionDialog(tk.Toplevel):
    def __init__(self, master, variables: List[str], initial: str, story: Story):
        super().__init__(master)
        self.title(tr("edit_actions"))
        self.resizable(False, False)
        self.result_ok = False
        self.variables = variables
        self.story = story
        self.actions_raw: List[Tuple[str, str, str]] = self._parse_initial(initial)

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
        acts: List[Tuple[str, str, str]] = []
        if not expr:
            return acts
        parts = [p.strip() for p in expr.split(";") if p.strip()]
        for part in parts:
            m = re.match(r"\s*(\w+)\s*(=|\+=|-=|\*=|/=|//=|%=|\*\*=)\s*(.+)\s*", part)
            if m:
                acts.append((m.group(1), m.group(2), m.group(3)))
        return acts

    def _refresh_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for var, op, val in self.actions_raw:
            self.tree.insert("", tk.END, values=(var, op, val))

    def _add(self):
        dlg = ConditionRowDialog(self, self.variables, None, ASSIGNMENT_OPERATORS)
        if dlg.result_ok and dlg.condition:
            self.actions_raw.append(dlg.condition)
            self._refresh_tree()

    def _edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        dlg = ConditionRowDialog(self, self.variables, self.actions_raw[idx], ASSIGNMENT_OPERATORS)
        if dlg.result_ok and dlg.condition:
            self.actions_raw[idx] = dlg.condition
            self._refresh_tree()

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        self.actions_raw.pop(idx)
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
            editor._update_code_editor()
            editor.undo_manager.record()

    def _ok(self):
        self.action_str = "; ".join(f"{v} {op} {val}" for v, op, val in self.actions_raw)
        self.actions: List[Action] = []
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
        for v, op, val in self.actions_raw:
            try:
                parsed = self._parse_value(val)
                if op == "=":
                    self.actions.append(Action(op="set", var=v, value=parsed))
                else:
                    self.actions.append(Action(op=op_map[op], var=v, value=parsed))
            except Exception:
                self.actions.append(Action(op="expr", var=v, value=val))
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()

    def _parse_value(self, token: str) -> Union[int, float, bool, str]:
        t = token.lower()
        if t == "true":
            return True
        if t == "false":
            return False
        if (token.startswith('"') and token.endswith('"')) or (
            token.startswith("'") and token.endswith("'")
        ):
            return ast.literal_eval(token)
        try:
            return int(token)
        except ValueError:
            try:
                return float(token)
            except ValueError:
                return token


class ConditionDialog(tk.Toplevel):
    def __init__(self, master, variables: List[str], initial: str):
        super().__init__(master)
        self.title(tr("edit_conditions"))
        self.resizable(False, False)
        self.result_ok = False
        self.variables = variables

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frm, columns=("kind", "expr"), show="tree")
        self.tree.grid(row=0, column=0, sticky="nsew")

        btns = ttk.Frame(frm)
        btns.grid(row=0, column=1, sticky="ns", padx=(8,0))
        ttk.Button(btns, text=tr("add"), command=self._add_condition).grid(row=0, column=0, pady=2)
        ttk.Button(btns, text="Add AND", command=lambda: self._add_group("and")).grid(row=1, column=0, pady=2)
        ttk.Button(btns, text="Add OR", command=lambda: self._add_group("or")).grid(row=2, column=0, pady=2)
        ttk.Button(btns, text=tr("edit"), command=self._edit).grid(row=3, column=0, pady=2)
        ttk.Button(btns, text=tr("delete"), command=self._delete).grid(row=4, column=0, pady=2)

        bottom = ttk.Frame(frm)
        bottom.grid(row=1, column=0, columnspan=2, sticky="e", pady=(8,0))
        ok = ttk.Button(bottom, text=tr("ok"), command=self._ok)
        cancel = ttk.Button(bottom, text=tr("cancel"), command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        self.root_item = self.tree.insert("", tk.END, text="AND", values=("op", "and"))
        self._parse_initial(initial)

        self.tree.bind("<ButtonPress-1>", self._start_drag)
        self.tree.bind("<ButtonRelease-1>", self._drop)

        self.grab_set()
        self.tree.focus_set()
        self.wait_window(self)

    def _start_drag(self, event):
        self._drag_item = self.tree.identify_row(event.y)

    def _drop(self, event):
        if not getattr(self, "_drag_item", None):
            return
        target = self.tree.identify_row(event.y)
        if not target:
            target = self.root_item
        kind = self.tree.set(target, "kind")
        if kind != "op":
            target = self.tree.parent(target)
        self.tree.move(self._drag_item, target, "end")
        self._drag_item = None

    def _add_condition(self):
        sel = self.tree.selection()
        parent = sel[0] if sel and self.tree.set(sel[0], "kind") == "op" else self.tree.parent(sel[0]) if sel else self.root_item
        dlg = ConditionRowDialog(self, self.variables, None, COMPARISON_OPERATORS)
        if dlg.result_ok and dlg.condition:
            expr = f"{dlg.condition[0]} {dlg.condition[1]} {dlg.condition[2]}"
            self.tree.insert(parent, tk.END, text=expr, values=("cond", expr))

    def _add_group(self, op: str):
        sel = self.tree.selection()
        parent = sel[0] if sel and self.tree.set(sel[0], "kind") == "op" else self.tree.parent(sel[0]) if sel else self.root_item
        text = op.upper()
        self.tree.insert(parent, tk.END, text=text, values=("op", op))

    def _edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        kind = self.tree.set(item, "kind")
        if kind == "cond":
            expr = self.tree.set(item, "expr")
            m = re.match(r"(\w+)\s*(==|!=|>=|<=|>|<)\s*(.+)", expr)
            initial = m.groups() if m else None
            dlg = ConditionRowDialog(self, self.variables, initial, COMPARISON_OPERATORS)
            if dlg.result_ok and dlg.condition:
                expr = f"{dlg.condition[0]} {dlg.condition[1]} {dlg.condition[2]}"
                self.tree.item(item, text=expr, values=("cond", expr))
        else:
            op = self.tree.set(item, "expr")
            new_op = "or" if op == "and" else "and"
            self.tree.item(item, text=new_op.upper(), values=("op", new_op))

    def _delete(self):
        sel = self.tree.selection()
        if not sel or sel[0] == self.root_item:
            return
        self.tree.delete(sel[0])

    def _parse_initial(self, expr: str):
        expr = expr.strip()
        if not expr:
            return
        try:
            tree = ast.parse(expr, mode="eval")
        except Exception:
            return
        def build(node, parent):
            if isinstance(node, ast.BoolOp):
                op = "and" if isinstance(node.op, ast.And) else "or"
                item = self.tree.insert(parent, tk.END, text=op.upper(), values=("op", op))
                for v in node.values:
                    build(v, item)
            else:
                expr = ast.unparse(node) if hasattr(ast, "unparse") else ""
                self.tree.insert(parent, tk.END, text=expr, values=("cond", expr))
        build(tree.body, self.root_item)

    def _expr_from_item(self, item: str) -> str:
        kind = self.tree.set(item, "kind")
        expr = self.tree.set(item, "expr")
        if kind == "cond":
            return expr
        children = self.tree.get_children(item)
        parts = [self._expr_from_item(c) for c in children]
        if not parts:
            return "1" if expr == "and" else "0"
        sep = f" {expr} "
        if len(parts) == 1:
            return parts[0]
        return "(" + sep.join(parts) + ")"

    def _ok(self):
        self.condition_str = self._expr_from_item(self.root_item)
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
        self.ent_text.bind("<KeyRelease>", lambda e: highlight_variables(self.ent_text, lambda: self.variables))
        highlight_variables(self.ent_text, lambda: self.variables)
        if hasattr(master, "register_var_drop_target"):
            master.register_var_drop_target(self.ent_text)

        ttk.Label(frm, text=tr("target_branch_id")).grid(row=2, column=0, sticky="w")
        self.cmb_target = ttk.Combobox(frm, values=branch_ids, state="readonly", width=30)
        self.cmb_target.grid(row=3, column=0, sticky="w")

        ttk.Label(frm, text=tr("condition_expr")).grid(row=4, column=0, sticky="w")
        cond_frame = ttk.Frame(frm)
        cond_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0,8))
        cond_frame.columnconfigure(0, weight=1)
        self.ent_cond = ttk.Entry(cond_frame, width=50, state="readonly")
        self.ent_cond.grid(row=0, column=0, sticky="ew")
        ttk.Button(cond_frame, text=tr("edit_ellipsis"), command=self._open_cond_editor).grid(row=0, column=1, padx=(4,0))

        ttk.Label(frm, text=tr("action_expr")).grid(row=6, column=0, sticky="w")
        act_frame = ttk.Frame(frm)
        act_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0,8))
        act_frame.columnconfigure(0, weight=1)
        self.ent_act = ttk.Entry(act_frame, width=50, state="readonly")
        self.ent_act.grid(row=0, column=0, sticky="ew")
        ttk.Button(act_frame, text=tr("edit_ellipsis"), command=self._open_act_editor).grid(row=0, column=1, padx=(4,0))

        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, sticky="e", pady=(10,0))
        ok = ttk.Button(btns, text=tr("ok"), command=self._ok)
        cancel = ttk.Button(btns, text=tr("cancel"), command=self._cancel)
        ok.grid(row=0, column=0, padx=5)
        cancel.grid(row=0, column=1)

        if choice:
            self.ent_text.insert("1.0", choice.text)
            highlight_variables(self.ent_text, lambda: self.variables)
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
            if getattr(choice, "actions", None):
                self.choice_actions = list(choice.actions)
                self.ent_act.configure(state="normal")
                self.ent_act.delete(0, tk.END)
                self.ent_act.insert(0, "; ".join(self._format_action(a) for a in choice.actions))
                self.ent_act.configure(state="readonly")
        else:
            if branch_ids:
                self.cmb_target.current(0)
        if not hasattr(self, "choice_actions"):
            self.choice_actions: List[Action] = []

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
        self.choice = Choice(text=text, target_id=target, condition=(cond or None), actions=list(self.choice_actions))
        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()

    def _open_cond_editor(self):
        dlg = ConditionDialog(self, self.variables, self.ent_cond.get().strip())
        if dlg.result_ok:
            self.ent_cond.configure(state="normal")
            self.ent_cond.delete(0, tk.END)
            self.ent_cond.insert(0, dlg.condition_str)
            self.ent_cond.configure(state="readonly")

    def _open_act_editor(self):
        dlg = ActionDialog(self, self.variables, self.ent_act.get().strip(), self.master.story)
        if dlg.result_ok:
            self.ent_act.configure(state="normal")
            self.ent_act.delete(0, tk.END)
            self.ent_act.insert(0, dlg.action_str)
            self.ent_act.configure(state="readonly")
            self.choice_actions = dlg.actions

    def _format_action(self, act: Action) -> str:
        op_map = {
            "set": "=",
            "add": "+=",
            "sub": "-=",
            "mul": "*=",
            "div": "/=",
            "floordiv": "//=",
            "mod": "%=",
            "pow": "**=",
            "expr": "=",
        }
        val = act.value
        if isinstance(val, bool):
            v = str(val).lower()
        elif isinstance(val, str):
            v = val
        else:
            v = str(val)
        return f"{act.var} {op_map.get(act.op, '=')} {v}"

class ChapterEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        icon_path = os.path.join(
            getattr(sys, "_MEIPASS", os.path.dirname(__file__)),
            "assets",
            "icons",
            "editoricon.png",
        )
        if os.path.exists(icon_path):
            try:
                self.iconphoto(True, tk.PhotoImage(file=icon_path))
            except tk.TclError:
                pass

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
        self.code_modified: bool = False
        self._drag_var_name: Optional[str] = None
        self._drag_label: Optional[tk.Toplevel] = None
        self._var_drop_targets: set[tk.Widget] = set()
        self._code_updating: bool = False

        self.undo_manager = UndoManager(self._capture_state, self._restore_state)

        self._build_menu()
        self._build_ui()
        self._refresh_chapter_list()
        # initialize editor with the first chapter
        self._load_chapter_to_form(ch_id)
        self._refresh_meta_panel()
        self._update_code_editor()

        # 찾기/변경 상태
        self.find_results: List[Tuple[str, int]] = []
        self.find_index: int = -1
        self._last_find_text: str = ""
        self._last_find_scope: str = "branch"

        # 창 닫힘 이벤트에 종료 처리 연결
        self.protocol("WM_DELETE_WINDOW", self._exit_app)

    def _capture_state(self):
        return {
            "story": copy.deepcopy(self.story),
            "current_chapter_id": self.current_chapter_id,
            "current_branch_id": self.current_branch_id,
        }

    def _restore_state(self, state: Dict[str, Any]):
        self.story = copy.deepcopy(state["story"])
        self.current_chapter_id = state["current_chapter_id"]
        self.current_branch_id = state["current_branch_id"]
        self._refresh_chapter_list()
        if self.current_chapter_id:
            self._load_chapter_to_form(self.current_chapter_id)
        self._set_dirty(True)

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
        em.add_command(label=tr("undo"), command=self.undo_manager.undo, accelerator="Ctrl+Z")
        em.add_command(label=tr("redo"), command=self.undo_manager.redo, accelerator="Ctrl+Y")
        em.add_separator()
        em.add_command(label=tr("add_chapter"), command=self._add_chapter, accelerator="Ctrl+Shift+A")
        em.add_command(label=tr("delete_chapter"), command=self._delete_current_chapter, accelerator="Del")
        em.add_separator()
        em.add_command(label=tr("find_replace"), command=self._open_find_window, accelerator="Ctrl+F")
        m.add_cascade(label=tr("edit_menu"), menu=em)

        lm = tk.Menu(m, tearoff=0)
        lm.add_command(label="English / 영어", command=lambda: self._change_language("en"))
        lm.add_command(label="한국어 / Korean", command=lambda: self._change_language("korean"))
        m.add_cascade(label="Language / 언어", menu=lm)

        self.config(menu=m)

        self.bind_all("<Control-n>", lambda e: self._new_story())
        self.bind_all("<Control-o>", lambda e: self._open_file())
        self.bind_all("<Control-s>", lambda e: self._save_file())
        self.bind_all("<Delete>", lambda e: self._delete_current_chapter())
        self.bind_all("<Control-Shift-A>", lambda e: self._add_chapter())
        self.bind_all("<Control-f>", lambda e: self._open_find_window())
        self.bind_all("<Control-z>", lambda e: self.undo_manager.undo())
        self.bind_all("<Control-y>", lambda e: self.undo_manager.redo())

    def _change_language(self, lang: str) -> None:
        set_language(lang)
        lang_file = get_user_lang_file("editor_language.txt")
        try:
            with open(lang_file, "w", encoding="utf-8") as f:
                f.write(lang)
            messagebox.showinfo("Language / 언어", tr("language_change_restart"))
        except OSError as e:
            messagebox.showerror(tr("error"), str(e))

    def _build_ui(self):
        # 좌: 메타 + 챕터 리스트, 우: 챕터 편집 + 선택지 + 코드 편집기
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
        self.ent_title.bind("<KeyRelease>", lambda e: self._on_title_changed())

        ttk.Label(meta, text=tr("start_branch_label")).grid(row=1, column=0, sticky="w")
        self.cmb_start = ttk.Combobox(meta, values=[], state="readonly")
        self.cmb_start.grid(row=1, column=1, sticky="ew")
        self.cmb_start.bind("<<ComboboxSelected>>", lambda e: self._on_start_changed())

        ttk.Label(meta, text=tr("ending_text_label")).grid(row=2, column=0, sticky="w")
        self.ent_end = ttk.Entry(meta, width=30)
        self.ent_end.grid(row=2, column=1, sticky="ew")
        self.ent_end.insert(0, self.story.ending_text)
        self.ent_end.bind("<KeyRelease>", lambda e: self._on_ending_changed())
        if hasattr(self, "register_var_drop_target"):
            self.register_var_drop_target(self.ent_end)

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
        self.tree_vars.bind("<ButtonPress-1>", self._on_var_drag_start)

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

        # 우측 편집/코드 편집기 영역
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
        self.ent_ch_title.bind("<KeyRelease>", lambda e: highlight_variables(self.ent_ch_title, lambda: self._collect_variables()))
        highlight_variables(self.ent_ch_title, lambda: self._collect_variables())
        self.register_var_drop_target(self.ent_ch_title)

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
        self.ent_br_title.bind("<KeyRelease>", lambda e: highlight_variables(self.ent_br_title, lambda: self._collect_variables()))
        highlight_variables(self.ent_br_title, lambda: self._collect_variables())
        self.register_var_drop_target(self.ent_br_title)

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
        self.txt_body.bind("<KeyRelease>", lambda e: highlight_variables(self.txt_body, lambda: self._collect_variables()))
        highlight_variables(self.txt_body, lambda: self._collect_variables())
        self.register_var_drop_target(self.txt_body)
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

        # 코드 편집기 탭
        code_tab = ttk.Frame(right, padding=8)
        right.add(code_tab, text=tr("code_editor_tab"))
        code_tab.rowconfigure(0, weight=1)
        code_tab.columnconfigure(0, weight=1)

        self.txt_code = tk.Text(
            code_tab,
            wrap="none",
            font=("Consolas", 11) if sys.platform.startswith("win") else ("Menlo", 11),
            undo=True,
        )
        self.txt_code.grid(row=0, column=0, sticky="nsew")
        pvx = ttk.Scrollbar(code_tab, orient="horizontal", command=self.txt_code.xview)
        pvy = ttk.Scrollbar(code_tab, orient="vertical", command=self.txt_code.yview)
        pvx.grid(row=1, column=0, sticky="ew")
        pvy.grid(row=0, column=1, sticky="ns")
        self.txt_code.configure(xscrollcommand=pvx.set, yscrollcommand=pvy.set)
        self.txt_code.bind("<<Modified>>", self._on_code_modified)
        self.txt_code.edit_modified(False)

        # 찾기/변경은 새 창에서 열림
        self.find_win = None

        # 하단 버튼 바
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        # 왼쪽: 분석/검사
        left_btns = ttk.Frame(bottom)
        left_btns.pack(side="left")
        ttk.Button(left_btns, text=tr("validate_story"), command=self._validate_story).pack(side="left")
        # 오른쪽: 저장/실행
        right_btns = ttk.Frame(bottom)
        right_btns.pack(side="right")
        ttk.Button(right_btns, text=tr("save"), command=self._save_file).pack(side="right")
        ttk.Button(right_btns, text=tr("run_story_btn"), command=self._run_story).pack(side="right", padx=(0, 6))

        root.pack(fill="both", expand=True)

    def register_var_drop_target(self, widget: tk.Widget) -> None:
        self._var_drop_targets.add(widget)
        widget.bind("<Destroy>", lambda e, w=widget: self._var_drop_targets.discard(w))

    def _on_var_drag_start(self, event):
        item = self.tree_vars.identify_row(event.y)
        if not item:
            return
        self._drag_var_name = self.tree_vars.item(item, "values")[0]
        self.bind_all("<Motion>", self._on_var_drag_motion)
        self.bind_all("<ButtonRelease-1>", self._on_var_drag_release)
        self._drag_label = tk.Toplevel(self)
        self._drag_label.overrideredirect(True)
        ttk.Label(self._drag_label, text=self._drag_var_name).pack()
        self._drag_label.geometry(f"+{event.x_root+10}+{event.y_root+10}")

    def _on_var_drag_motion(self, event):
        if not self._drag_var_name:
            return
        if self._drag_label:
            self._drag_label.geometry(f"+{event.x_root+10}+{event.y_root+10}")
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget in self._var_drop_targets:
            x = event.x_root - widget.winfo_rootx()
            y = event.y_root - widget.winfo_rooty()
            if isinstance(widget, tk.Text):
                idx = widget.index(f"@{x},{y}")
                widget.mark_set("insert", idx)
                widget.focus_force()
            else:
                try:
                    idx = widget.index(f"@{x}")
                except tk.TclError:
                    idx = widget.index(tk.INSERT)
                widget.icursor(idx)
                widget.focus_force()

    def _on_var_drag_release(self, event):
        if not self._drag_var_name:
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget in self._var_drop_targets:
            x = event.x_root - widget.winfo_rootx()
            y = event.y_root - widget.winfo_rooty()
            if isinstance(widget, tk.Text):
                idx = widget.index(f"@{x},{y}")
                widget.insert(idx, f"__{self._drag_var_name}__")
                highlight_variables(widget, lambda: self._collect_variables())
            else:
                try:
                    idx = widget.index(f"@{x}")
                except tk.TclError:
                    idx = widget.index(tk.INSERT)
                widget.insert(idx, f"__{self._drag_var_name}__")
            widget.focus_force()
        self._drag_var_name = None
        if self._drag_label:
            self._drag_label.destroy()
            self._drag_label = None
        self.unbind_all("<Motion>")
        self.unbind_all("<ButtonRelease-1>")

    # ---------- 핸들러 ----------
    def _on_title_changed(self):
        text = self.ent_title.get("1.0", "end-1c")
        if VAR_PATTERN.search(text):
            text = VAR_PATTERN.sub("", text)
            self.ent_title.delete("1.0", tk.END)
            self.ent_title.insert("1.0", text)
        self.story.title = text.strip() or "Untitled"
        self._set_dirty(True)
        self._update_code_editor()
        self.undo_manager.record()

    def _on_start_changed(self):
        sid = self.cmb_start.get().strip()
        if sid:
            self.story.start_id = sid
            self._set_dirty(True)
            self._update_code_editor()
            self.undo_manager.record()

    def _on_ending_changed(self):
        self.story.ending_text = self.ent_end.get().strip() or "The End"
        self._set_dirty(True)
        self._update_code_editor()
        self.undo_manager.record()

    def _on_show_disabled_changed(self):
        self.story.show_disabled = self.var_show_disabled.get()
        self._set_dirty(True)
        self._update_code_editor()
        self.undo_manager.record()

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
            self._update_code_editor()
            self.undo_manager.record()

    def _on_code_modified(self, evt):
        if self.txt_code.edit_modified():
            self.txt_code.edit_modified(False)
            if not self._code_updating:
                self.code_modified = True
                self._set_dirty(True)
                self.after(500, lambda: self._apply_code_to_model(silent=True))


    # ---------- 상호작용 ----------
    def _load_chapter_to_form(self, cid: str):
        self.current_chapter_id = cid
        ch = self.story.chapters[cid]
        self.ent_ch_id.delete(0, tk.END)
        self.ent_ch_id.insert(0, ch.chapter_id)
        self.ent_ch_title.delete("1.0", tk.END)
        self.ent_ch_title.insert("1.0", ch.title)
        highlight_variables(self.ent_ch_title, lambda: self._collect_variables())
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
        highlight_variables(self.ent_br_title, lambda: self._collect_variables())

        self.txt_body.config(state="normal")
        self.txt_body.delete("1.0", tk.END)
        if br.raw_text:
            self.txt_body.insert(tk.END, br.raw_text)
        elif br.paragraphs:
            self.txt_body.insert(tk.END, "\n\n".join(br.paragraphs))
        highlight_variables(self.txt_body, lambda: self._collect_variables())
        self.txt_body.edit_modified(False)

        for i in self.tree_choices.get_children():
            self.tree_choices.delete(i)
        for c in br.choices:
            self.tree_choices.insert("", tk.END, values=(c.text, c.target_id))

        self._refresh_meta_panel()
        self._update_code_editor()

    def _apply_body_to_model(self):
        if self.current_branch_id is None:
            return
        br = self.story.branches[self.current_branch_id]
        raw = self.txt_body.get("1.0", tk.END).rstrip("\n")
        br.raw_text = raw
        lines = raw.splitlines()
        parser = StoryParser()
        # Remove comment lines and inline comments so they don't appear
        # when running the game.
        lines = parser._remove_comments(lines)
        cleaned = "\n".join(lines)
        paras = [p.strip() for p in cleaned.split("\n\n")]
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
        self._update_code_editor()
        self.undo_manager.record()

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
        self._update_code_editor()
        self.undo_manager.record()

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
        self.undo_manager.record()

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
            self.undo_manager.record()

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
        self.undo_manager.record()

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
        self.undo_manager.record()

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
            self.undo_manager.record()

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
        self.undo_manager.record()

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
            if isinstance(val, bool):
                val_str = str(val).lower()
            elif isinstance(val, str):
                val_str = repr(val)
            else:
                val_str = val
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
            self._update_code_editor()
            self.undo_manager.record()

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
            self._update_code_editor()
            self.undo_manager.record()

    def _delete_variable(self):
        sel = self.tree_vars.selection()
        if not sel:
            return
        name = self.tree_vars.item(sel[0], "values")[0]
        if messagebox.askyesno(tr("confirm_delete"), tr("delete_variable_prompt", name=name)):
            self.story.variables.pop(name, None)
            self._refresh_variable_list()
            self._set_dirty(True)
            self._update_code_editor()
            self.undo_manager.record()

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
            self._update_code_editor()
            self.undo_manager.record()

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
            self._update_code_editor()
            self.undo_manager.record()

    def _delete_choice(self):
        sel = self.tree_choices.selection()
        if not sel or self.current_branch_id is None:
            return
        idx = self.tree_choices.index(sel[0])
        br = self.story.branches[self.current_branch_id]
        br.choices.pop(idx)
        self.tree_choices.delete(sel[0])
        self._set_dirty(True)
        self._update_code_editor()
        self.undo_manager.record()

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
        self._update_code_editor()
        self.undo_manager.record()

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
        highlight_variables(self.txt_body, lambda: self._collect_variables())
        self._apply_body_to_model()
        self._build_find_results(query, self.find_scope.get())
        self._find_step(1)

    def _merge_comments(self, original: str, updated: str) -> str:
        parser = StoryParser()
        orig_lines = original.splitlines()
        upd_lines = updated.splitlines()
        comments_before: Dict[int, List[str]] = {}
        inline_comments: Dict[int, str] = {}
        buffer: List[str] = []
        idx = 0
        in_block = False
        for line in orig_lines:
            stripped = line.strip()
            if stripped == ';':
                buffer.append(line)
                in_block = not in_block
                continue
            if in_block:
                buffer.append(line)
                continue
            if stripped.startswith(';'):
                buffer.append(line)
                continue
            base = parser._strip_inline_comment(line)
            comment_part = line[len(base):]
            comments_before[idx] = buffer
            inline_comments[idx] = comment_part
            buffer = []
            idx += 1
        trailing = buffer

        merged: List[str] = []
        recent_comments: List[str] = []
        idx = 0  # index for non-comment lines
        for line in upd_lines:
            stripped = line.strip()
            if stripped.startswith(';'):
                merged.append(line)
                recent_comments.append(line)
            else:
                existing = set(recent_comments)
                for c in comments_before.get(idx, []):
                    if c not in existing:
                        merged.append(c)
                        existing.add(c)
                base = parser._strip_inline_comment(line)
                if line[len(base):]:
                    merged.append(line)
                else:
                    merged.append(line + inline_comments.get(idx, ""))
                recent_comments = []
                idx += 1
        if trailing:
            for c in trailing:
                # 중간 입력 과정에서 생성된 이전 주석 조각들이
                # ``recent_comments`` 에 있는 최신 주석의 접두사/접미사로
                # 남아 중복되는 문제가 있었다. 두 주석이 서로의 접두사
                # 관계에 있으면 동일한 주석으로 간주하여 병합에서 제외한다.
                if c not in recent_comments and not any(rc.startswith(c) or c.startswith(rc) for rc in recent_comments):
                    merged.append(c)
        return "\n".join(merged)

    def _update_code_editor(self, force: bool = False):
        # 사용자가 코드 편집기를 수정했을 때는 기본 덮어쓰기를 막는다.
        # 단, 의도적으로 버리기/강제 동기화가 필요할 땐 force=True로 호출.
        if self.code_modified and not force:
            return

        self._apply_body_to_model()

        parser = StoryParser()
        serialized = self.story.serialize().rstrip()
        current = self.txt_code.get("1.0", tk.END).rstrip("\n")
        txt = serialized if force else self._merge_comments(current, serialized)

        self._code_updating = True
        try:
            self.txt_code.delete("1.0", tk.END)
            self.txt_code.insert(tk.END, txt)
            self.txt_code.edit_modified(False)
        finally:
            self._code_updating = False

        self.code_modified = False

    def _apply_code_to_model(self, silent: bool = False) -> bool:
        if not self.code_modified:
            return True
        txt = self.txt_code.get("1.0", tk.END)
        parser = StoryParser()
        try:
            story = parser.parse(txt)
        except ParseError as e:
            if not silent:
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
        self._refresh_chapter_list()
        # 코드 편집기에서 변경된 메타데이터를 반영
        self._refresh_meta_panel()
        if self.current_chapter_id:
            self._load_chapter_to_form(self.current_chapter_id)
            if self.current_branch_id:
                self._load_branch_to_form(self.current_branch_id)
        else:
            self.txt_body.delete("1.0", tk.END)
            highlight_variables(self.txt_body, lambda: self._collect_variables())
            for i in self.tree_choices.get_children():
                self.tree_choices.delete(i)
        # 코드 편집기 텍스트의 수정 플래그 초기화
        self.txt_code.edit_modified(False)
        self.code_modified = False
        self._set_dirty(True)
        self.undo_manager.record()
        return True

    def _run_story(self):
        """branching_novel.py에 의존하지 않고 내장 실행기로 현재 스토리를 실행한다."""
        if not self._apply_code_to_model():
            return
        self._apply_body_to_model()

        import copy

        story_copy = copy.deepcopy(self.story)
        file_path = self.current_file or "<editor>"
        app = BranchingNovelApp(story_copy, file_path, show_disabled=self.story.show_disabled)
        app.mainloop()

    def _validate_story(self, auto: bool = False):
        if not self._apply_code_to_model():
            return
        self._apply_body_to_model()
        errors: List[str] = []
        warnings: List[str] = []

        def _line_info(line: int, src: str) -> str:
            return f" (line {line}: {src})" if line else ""

        if not self.story.title.strip():
            errors.append(tr("story_title_empty"))
        if not self.story.start_id or self.story.start_id not in self.story.branches:
            errors.append(tr("invalid_start"))

        ids = set(self.story.branches.keys())
        for bid, br in self.story.branches.items():
            if not br.branch_id.strip():
                errors.append(tr("branch_id_empty", id=bid) + _line_info(br.line, br.source))
            if br.branch_id != bid:
                errors.append(tr("branch_id_mismatch", id=bid, branch_id=br.branch_id) + _line_info(br.line, br.source))
            for c in br.choices:
                if c.target_id not in ids:
                    warnings.append(
                        tr("warn_choice_target_missing", id=bid, text=c.text, target=c.target_id)
                        + _line_info(c.line, c.source)
                    )

        for cid, ch in self.story.chapters.items():
            if not ch.branches:
                warnings.append(tr("warn_chapter_no_branches", id=cid) + _line_info(ch.line, ch.source))

        # numeric-only operator vs non-numeric variable check
        var_types: Dict[str, Set[type]] = {}
        for name, val in self.story.variables.items():
            var_types.setdefault(name, set()).add(type(val))
        for br in self.story.branches.values():
            for act in br.actions:
                if act.op == "expr":
                    # Expression results are dynamic; skip type inference to avoid false positives
                    continue
                val_type = type(act.value)
                var_types.setdefault(act.var, set()).add(val_type)
        numeric_ops = {"add", "sub", "mul", "div", "floordiv", "mod", "pow"}
        warned = set()
        for br in self.story.branches.values():
            for act in br.actions:
                if act.op in numeric_ops:
                    types = var_types.get(act.var, set())
                    if str in types:
                        key = (act.var, act.op)
                        if key not in warned:
                            warned.add(key)
                            warnings.append(
                                tr("warn_numeric_non_numeric", var=act.var, op=act.op)
                                + _line_info(act.line, act.source)
                            )

        msg = []
        if errors:
            msg.append(tr("errors_label"))
            msg.extend(f"- {e}" for e in errors)
        if warnings:
            if msg:
                msg.append("")
            msg.append(tr("warnings_label"))
            msg.extend(f"- {w}" for w in warnings)

        loop_lines, definite, witnessed, possible = self._analyze_infinite_loops(show_window=False)
        summary = [loop_lines[0], loop_lines[2]]
        if msg:
            msg.append("")
        msg.extend(summary)

        has_critical = bool(errors or definite or witnessed)
        if auto:
            if has_critical:
                self._show_validation_results(tr("validation_result_title"), msg)
                if definite or witnessed:
                    self._show_loop_analysis(loop_lines)
            else:
                return
        else:
            if errors or warnings or definite or witnessed or possible:
                self._show_validation_results(tr("validation_result_title"), msg)
            else:
                ok_lines = [tr("validation_ok"), ""]
                ok_lines.extend(summary)
                self._show_validation_results(tr("validation_title"), ok_lines)
            if definite or witnessed or possible:
                self._show_loop_analysis(loop_lines)

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
        self._refresh_chapter_list()
        self._load_chapter_to_form(ch_id)
        self._refresh_meta_panel()
        self._update_code_editor()
        self._set_dirty(False)
        self.undo_manager = UndoManager(self._capture_state, self._restore_state)

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
        self._refresh_chapter_list()
        if self.current_chapter_id:
            self._load_chapter_to_form(self.current_chapter_id)
            if self.current_branch_id:
                self._load_branch_to_form(self.current_branch_id)
        self._refresh_meta_panel()
        # Preserve original comments by using the raw text in the code editor
        self._code_updating = True
        try:
            self.txt_code.delete("1.0", tk.END)
            self.txt_code.insert(tk.END, text)
            self.txt_code.edit_modified(False)
        finally:
            self._code_updating = False
        self.code_modified = False
        self._set_dirty(False)
        self.undo_manager = UndoManager(self._capture_state, self._restore_state)
        self.title(f"Branching Novel Editor - {os.path.basename(path)}")
        self._validate_story(auto=True)

    def _save_file(self):
        if self.current_file is None:
            self._save_file_as()
            return
        if not self._apply_code_to_model():
            return
        self._apply_body_to_model()
        txt = self.txt_code.get("1.0", tk.END).rstrip("\n")
        if self.dirty:
            parser = StoryParser()
            serialized = self.story.serialize()
            clean_code = "\n".join(parser._remove_comments(txt.splitlines())).rstrip()
            if clean_code != serialized:
                # 본문에서 변경된 내용이 있다면 코드 편집기 갱신이 필요
                self._update_code_editor(force=True)
                txt = self.txt_code.get("1.0", tk.END).rstrip("\n")
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(txt + "\n")
        except Exception as e:
            messagebox.showerror(tr("error"), tr("save_error", err=e))
            return
        self._set_dirty(False)
        messagebox.showinfo(tr("save_title"), tr("save_done"))

    def _save_file_as(self):
        if not self._apply_code_to_model():
            return
        self._apply_body_to_model()
        path = filedialog.asksaveasfilename(
            title=tr("save_as_title"),
            defaultextension=".bnov",
            filetypes=[("Branching Novel Files","*.bnov"),("All Files","*.*")],
            initialfile="story.bnov",
        )
        if not path:
            return
        txt = self.txt_code.get("1.0", tk.END).rstrip("\n")
        if self.dirty:
            parser = StoryParser()
            serialized = self.story.serialize()
            clean_code = "\n".join(parser._remove_comments(txt.splitlines())).rstrip()
            if clean_code != serialized:
                self._update_code_editor(force=True)
                txt = self.txt_code.get("1.0", tk.END).rstrip("\n")
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
        # 더티 플래그가 있으면 저장 여부 확인
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
    def _analyze_infinite_loops(self, show_window: bool = True):
        """
        무한 루프 간단 리포트:
        - 강한 해석(가드 기반 고정점 + SCC + 경로 시뮬레이션)은 유지
        - 출력은 요약/조치 중심으로 간결화
        """
        import math

        story = self.story
        branches = story.branches
        start_id = story.start_id

        if not start_id or start_id not in branches:
            lines = [
                tr("loop_summary_heading"),
                "",
                tr("loop_summary_counts", definite=0, witnessed=0, possible=0),
            ]
            if show_window:
                self._show_loop_analysis(lines)
            return lines, [], [], []

        # -----------------------
        # 공용 유틸
        # -----------------------
        EPS = 1e-9
        BIG = 1e18

        def as_point(v):
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
                cur = st.get(var, as_point(0.0))
                val = act.value
                if not isinstance(val, (int, float)):
                    st[var] = widen_unknown(cur)
                    continue
                if act.op == "set":
                    st[var] = as_point(val)
                elif act.op == "add":
                    lo, hi = cur
                    st[var] = (lo + val, hi + val)
                elif act.op == "sub":
                    lo, hi = cur
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
                if not isinstance(b, (int, float)):
                    v[var] = float('nan')
                    continue
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
        initial = {k: as_point(v) for k, v in story.variables.items()}
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
        if show_window:
            self._show_loop_analysis(lines)
        return lines, definite, witnessed, possible

    def _show_validation_results(self, title: str, lines: List[str]) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("720x480")
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

    def _show_loop_analysis(self, lines: List[str]) -> None:
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
        lang_file = get_user_lang_file("editor_language.txt")
        set_language_from_file(lang_file)

    app = ChapterEditor()
    check_for_update(
        app_name=APP_NAME,
        installer_name=INSTALLER_NAME,
        app_id=APP_ID,
    )
    app.mainloop()

if __name__ == "__main__":
    main()
