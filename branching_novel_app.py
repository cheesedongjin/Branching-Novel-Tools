import sys
import os
import re
import ast
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
from pathlib import Path
from datetime import datetime

from i18n import tr, set_language, get_user_lang_file, get_app_data_dir
from story_parser import Choice, Action, Branch, Chapter, Story

VAR_PATTERN = re.compile(r"__([A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)__")


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

        # 테마 로드
        self.theme, self._theme_dir = self._load_theme()
        self._icon_image: Optional[tk.PhotoImage] = None

        # 상태 값과 옵션
        self.show_disabled = show_disabled
        self.state: Dict[str, Union[int, float, bool, str]] = {}

        # 히스토리와 현재 인덱스
        self.history: List[Step] = []
        self.current_index: int = -1  # history에서 현재 분기 위치
        self.visited_chapters: List[str] = []
        self.chapter_positions: List[int] = []  # 각 챕터의 시작 인덱스
        self.chapter_page_index: int = -1
        # data for scrolling long chapter titles
        self._marquee_items: List[Dict[str, Any]] = []
        self._marquee_job: Optional[str] = None
        self._marquee_pause_cycles: int = 10

        self._build_menu()
        self._build_ui()
        self._bind_events()

        # 시작 챕터로 이동
        self._reset_to_start()

    def _load_theme(self, name: str = "default") -> Tuple[Dict[str, Any], Path]:
        """Load theme configuration from the app data 'themes' folder.

        Returns a tuple of (theme_dict, theme_directory). If theme files are
        missing or invalid, built-in defaults are used.
        """
        base_dir = get_app_data_dir() / "themes"
        base_dir.mkdir(parents=True, exist_ok=True)
        theme_dir = base_dir
        theme_file = theme_dir / "theme.json"

        default = {
            "fonts": {
                "chapter": {"family": "Segoe UI", "size": 11, "weight": "bold"},
                "title": {"family": "Segoe UI", "size": 12, "weight": "bold"},
                "text": {"family": "Malgun Gothic", "size": 12}
                if sys.platform.startswith("win")
                else {"family": "Noto Sans CJK KR", "size": 12},
            },
            "colors": {"path": "#666666"},
            "icons": {"app": "appicon.png"},
        }

        if theme_file.exists():
            try:
                with open(theme_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key in ("fonts", "colors", "icons"):
                    if key in data:
                        default.setdefault(key, {}).update(data[key])
            except (OSError, json.JSONDecodeError):
                pass
        else:
            theme_dir = base_dir / name
            theme_file = theme_dir / "theme.json"
            if theme_file.exists():
                try:
                    with open(theme_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for key in ("fonts", "colors", "icons"):
                        if key in data:
                            default.setdefault(key, {}).update(data[key])
                except (OSError, json.JSONDecodeError):
                    pass

        return default, theme_dir

    def _build_menu(self) -> None:
        m = tk.Menu(self)

        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="Save Progress", command=self._save_progress)
        fm.add_command(label="Load Progress", command=self._load_progress)
        m.add_cascade(label="File", menu=fm)

        lm = tk.Menu(m, tearoff=0)
        lm.add_command(label="English / 영어", command=lambda: self._change_language("en"))
        lm.add_command(label="한국어 / Korean", command=lambda: self._change_language("korean"))
        m.add_cascade(label="Language / 언어", menu=lm)
        self.config(menu=m)

    def _change_language(self, lang: str) -> None:
        set_language(lang)
        lang_file = get_user_lang_file("game_language.txt")
        try:
            with open(lang_file, "w", encoding="utf-8") as f:
                f.write(lang)
            messagebox.showinfo("Language / 언어", tr("language_change_restart"))
        except OSError as e:
            messagebox.showerror(tr("error"), str(e))

    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "", name)

    def _save_directory(self) -> Path:
        game_name = self._sanitize_filename(self._interpolate(self.story.title))
        if sys.platform.startswith("win"):
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path.home() / ".local" / "share"
        directory = base / game_name / "saves"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _save_progress(self) -> None:
        data = {
            "history": [step.__dict__ for step in self.history],
            "current_index": self.current_index,
            "state": self.state,
        }
        save_dir = self._save_directory()
        game_title = self._sanitize_filename(self._interpolate(self.story.title))
        chapter_title = ""
        br = self._current_branch()
        if br:
            ch = self.story.get_chapter(br.chapter_id)
            if ch and ch.title:
                chapter_title = self._sanitize_filename(self._interpolate(ch.title))
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        parts = [game_title]
        if chapter_title:
            parts.append(chapter_title)
        parts.append(timestamp)
        filename = "-".join(parts) + ".json"
        path = filedialog.asksaveasfilename(
            title="Save Progress",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*")],
            initialdir=save_dir,
            initialfile=filename,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror(tr("error"), str(e))

    def _load_progress(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Progress",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*")],
            initialdir=self._save_directory(),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror(tr("error"), str(e))
            return

        hist = data.get("history", [])
        self.history = [Step(branch_id=h.get("branch_id", ""), chosen_text=h.get("chosen_text")) for h in hist]
        self.current_index = data.get("current_index", len(self.history) - 1)
        self.state = data.get("state", {})

        # rebuild chapter visit data
        self.visited_chapters.clear()
        self.chapter_positions.clear()
        for idx, step in enumerate(self.history):
            br = self.story.get_branch(step.branch_id)
            if not br:
                continue
            if not self.visited_chapters or self.visited_chapters[-1] != br.chapter_id:
                self.visited_chapters.append(br.chapter_id)
                self.chapter_positions.append(idx)
        self.chapter_page_index = 0
        for i, pos in enumerate(self.chapter_positions):
            if pos <= self.current_index:
                self.chapter_page_index = i
            else:
                break

        self._populate_chapter_list()
        self._render_current()

    def _build_ui(self):
        # 아이콘 적용
        icons = self.theme.get("icons", {})
        app_icon = icons.get("app")
        icon_path = self._theme_dir / app_icon if app_icon else None
        if icon_path and icon_path.exists():
            self._icon_image = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(False, self._icon_image)

        # 폰트 및 색상 설정
        fonts = self.theme.get("fonts", {})
        colors = self.theme.get("colors", {})

        def _get_font(name: str, fallback: Dict[str, Any]) -> tkfont.Font:
            spec = fonts.get(name, fallback).copy()
            file = spec.pop("file", None)
            if file:
                spec["file"] = str(self._theme_dir / file)
            return tkfont.Font(**spec)

        chapter_font = _get_font("chapter", {"family": "Segoe UI", "size": 11, "weight": "bold"})
        title_font = _get_font("title", {"family": "Segoe UI", "size": 12, "weight": "bold"})
        text_default = {"family": "Malgun Gothic", "size": 12} if sys.platform.startswith("win") else {"family": "Noto Sans CJK KR", "size": 12}
        text_font = _get_font("text", text_default)
        path_color = colors.get("path", "#666666")

        self._fonts = {"chapter": chapter_font, "title": title_font, "text": text_font}

        # 전체 수직 레이아웃: 좌측 챕터 리스트, 우측 본문/선택/네비
        self.columnconfigure(0, weight=0)  # left panel width fixed
        self.columnconfigure(1, weight=1)  # right panel expands
        self.rowconfigure(0, weight=1)

        # 좌측: 챕터 리스트 패널
        left_frame = ttk.Frame(self, padding=(8, 8, 8, 8))
        left_frame.grid(row=0, column=0, sticky="nsw")
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        ttk.Label(left_frame, text="Chapters", font=chapter_font).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.chapter_list = tk.Listbox(left_frame, exportselection=False, height=25, font=chapter_font)
        self.chapter_list.grid(row=1, column=0, sticky="nsw")
        # 사용자 클릭/포커스 방지
        self.chapter_list.configure(state="disabled", takefocus=0)
        self._populate_chapter_list()
        # start scrolling for long titles after widget rendered
        self.after(100, self._setup_chapter_marquee)

        # 우측: 상단 네비게이션 바
        right_frame = ttk.Frame(self, padding=(8, 8, 8, 8))
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(2, weight=1)

        nav_frame = ttk.Frame(right_frame)
        nav_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        nav_frame.columnconfigure(1, weight=1)

        self.title_label = ttk.Label(nav_frame, text=self._interpolate(self.story.title), font=title_font)
        self.title_label.grid(row=0, column=0, sticky="w")

        self.path_label = ttk.Label(nav_frame, text="", foreground=path_color, font=chapter_font)
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
            text_frame, wrap="word", state="disabled", relief="flat", font=text_font
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
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self._marquee_job:
            self.after_cancel(self._marquee_job)
            self._marquee_job = None
        self.destroy()

    def _populate_chapter_list(self):
        if self._marquee_job:
            self.after_cancel(self._marquee_job)
            self._marquee_job = None
        self._marquee_items = []
        # 리스트 업데이트 시 일시적으로 활성화
        self.chapter_list.configure(state="normal")
        self.chapter_list.delete(0, tk.END)
        for cid in self.visited_chapters:
            ch = self.story.get_chapter(cid)
            title = self._interpolate(ch.title) if ch and ch.title else ""
            item = f"{cid} | {title}" if title else cid
            self.chapter_list.insert(tk.END, item)
        self.chapter_list.configure(state="disabled")
        # recompute marquee data when list changes
        self.after(100, self._setup_chapter_marquee)

    def _setup_chapter_marquee(self):
        if self._marquee_job:
            self.after_cancel(self._marquee_job)
            self._marquee_job = None
        # make sure geometry info is up-to-date before measuring width
        self.chapter_list.update_idletasks()
        width = self.chapter_list.winfo_width()
        if width <= 1:
            # widget not yet rendered; try again shortly
            self._marquee_job = self.after(100, self._setup_chapter_marquee)
            return
        font = tkfont.nametofont(self.chapter_list.cget("font"))
        self._marquee_items = []
        for i in range(self.chapter_list.size()):
            text = self.chapter_list.get(i)
            if font.measure(text) > width:
                self._marquee_items.append({"index": i, "text": text, "offset": 0, "pause": 0})
        if self._marquee_items:
            self._marquee_job = self.after(300, self._step_chapter_marquee)

    def _step_chapter_marquee(self):
        if not self._marquee_items:
            self._marquee_job = None
            return
        sel = self.chapter_list.curselection()
        self.chapter_list.configure(state="normal")
        for item in self._marquee_items:
            full = item["text"] + "   "
            if item["pause"] > 0:
                item["pause"] -= 1
                continue
            # advance offset before rendering so the loop completes
            item["offset"] = (item["offset"] + 1) % len(full)
            display = full[item["offset"]:] + full[: item["offset"]]
            self.chapter_list.delete(item["index"])
            self.chapter_list.insert(item["index"], display)
            if item["offset"] == 0:
                item["pause"] = self._marquee_pause_cycles
        if sel:
            self.chapter_list.selection_clear(0, tk.END)
            self.chapter_list.selection_set(sel[0])
            self.chapter_list.see(sel[0])
        self.chapter_list.configure(state="disabled")
        self._marquee_job = self.after(300, self._step_chapter_marquee)

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
                lines.append("\n\n".join(self._interpolate(p) for p in br.paragraphs))
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

        # 현재 상태와 초기 변수 병합
        variables = {**self.story.variables, **self.state}

        s = text
        out_parts: List[str] = []
        i = 0
        n = len(s)

        # 커스텀 스캐너: '__name__' 패턴을 직접 파싱
        # 규칙:
        #  - 올바른 플레이스홀더: '__' + [A-Za-z0-9]+(?:_[A-Za-z0-9]+)* + '__'
        #  - 정의된 변수면 값을 치환하고 끝 인덱스까지 소비
        #  - 미정의 변수면 '__name'까지만 출력하고, 뒤의 '__'는 소비하지 않아
        #    다음 루프에서 새 토큰의 시작으로 재인식되게 함
        while i < n:
            j = s.find("__", i)
            if j == -1:
                out_parts.append(s[i:])
                break

            # 앞부분 그대로 출력
            out_parts.append(s[i:j])

            # '__' 다음에서 식별자 파싱 시도
            k = j + 2
            m = re.match(r"([A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)", s[k:])
            if not m:
                # 슬라이딩: '___var__'처럼 '__' 뒤에 식별자가 없으면 '_'만 소비하고 한 칸 전진
                out_parts.append("_")
                i = j + 1
                continue

            name = m.group(1)
            k += m.end()  # name 직후 위치

            # 닫힘 '__' 확인
            if k + 2 <= n and s.startswith("__", k):
                if name in variables:
                    # 정의된 변수: 값으로 치환하고 전체 토큰 소비
                    out_parts.append(str(variables[name]))
                    i = k + 2
                else:
                    # 미정의 변수: '__name'만 내보내고, 닫힘 '__'는 소비하지 않음
                    # 다음 반복에서 그 '__'가 새로운 토큰 시작으로 사용될 수 있음
                    out_parts.append(s[j:k])
                    i = k
            else:
                # 슬라이딩: 닫힘 '__'가 없으면 '_'만 소비하고 한 칸 전진
                out_parts.append("_")
                i = j + 1

        return "".join(out_parts)

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


