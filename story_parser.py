import re
import ast
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union

@dataclass
class Choice:
    text: str
    target_id: str
    condition: Optional[str] = None
    line: int = 0
    source: str = ""

@dataclass
class Action:
    op: str  # e.g. 'set', 'add', 'sub', 'mul', 'div', 'floordiv', 'mod', 'pow', 'expr'
    var: str
    value: Union[int, float, bool, str]
    line: int = 0
    source: str = ""

@dataclass
class Branch:
    branch_id: str
    title: str
    chapter_id: str
    paragraphs: List[str] = field(default_factory=list)
    choices: List[Choice] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    line: int = 0
    source: str = ""


@dataclass
class Chapter:
    chapter_id: str
    title: str
    branches: Dict[str, Branch] = field(default_factory=dict)
    line: int = 0
    source: str = ""

@dataclass
class Story:
    title: str = "Untitled"
    start_id: Optional[str] = None  # 시작 분기 ID
    ending_text: str = "The End"
    show_disabled: bool = False
    chapters: Dict[str, Chapter] = field(default_factory=dict)
    branches: Dict[str, Branch] = field(default_factory=dict)
    variables: Dict[str, Union[int, float, bool, str]] = field(default_factory=dict)

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
            if isinstance(val, bool):
                val_str = str(val).lower()
            elif isinstance(val, str):
                val_str = repr(val)
            else:
                val_str = val
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
                    if act.op == "expr":
                        lines.append(f"! {act.var} = {act.value}")
                    else:
                        if isinstance(act.value, bool):
                            v = str(act.value).lower()
                        elif isinstance(act.value, str):
                            v = repr(act.value)
                        else:
                            v = act.value
                        if act.op == "set":
                            lines.append(f"! {act.var} = {v}")
                        else:
                            sym = op_map.get(act.op)
                            if sym:
                                lines.append(f"! {act.var} {sym} {v}")
                for c in br.choices:
                    if c.condition:
                        lines.append(f"* [{c.condition}] {c.text} -> {c.target_id}")
                    else:
                        lines.append(f"* {c.text} -> {c.target_id}")
                lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

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
            if line.startswith(";"):
                continue
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
            line_no = i + 1
            i += 1

            if stripped.startswith(";"):
                continue

            if stripped.startswith(("@title:", "@start:", "@ending:", "@show-disabled:")):
                continue

            if stripped.startswith("@chapter"):
                current_branch = None
                current_chapter = self._parse_chapter_decl(stripped, line_no, line)
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
                current_branch = self._parse_branch_header(stripped, current_chapter.chapter_id, line_no, line)
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
                action = self._parse_action_line(stripped, line_no, line)
                if current_branch is None:
                    if action.op == "set":
                        story.variables[action.var] = action.value
                    elif action.op == "expr":
                        try:
                            story.variables[action.var] = eval(action.value, {}, dict(story.variables))
                        except Exception:
                            raise ParseError("Invalid expression for initial variable.")
                    else:
                        raise ParseError("State change found outside of any branch.")
                else:
                    current_branch.actions.append(action)
                continue

            if stripped.startswith("* "):
                if current_branch is None:
                    raise ParseError("Choice found outside of any branch.")
                choice = self._parse_choice_line(stripped, line_no, line)
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

    def _parse_chapter_decl(self, line: str, line_no: int, source: str) -> Chapter:
        content = line[len("@chapter"):].strip()
        if ":" in content:
            cid, title = content.split(":", 1)
            return Chapter(chapter_id=cid.strip(), title=title.strip(), line=line_no, source=source)
        return Chapter(chapter_id=content.strip(), title=content.strip(), line=line_no, source=source)

    def _parse_branch_header(self, header_line: str, chapter_id: str, line_no: int, source: str) -> Branch:
        content = header_line.lstrip("#").strip()
        if ":" in content:
            bid, title = content.split(":", 1)
            return Branch(branch_id=bid.strip(), title=title.strip(), chapter_id=chapter_id, line=line_no, source=source)
        else:
            bid = content.strip()
            return Branch(branch_id=bid, title=bid, chapter_id=chapter_id, line=line_no, source=source)

    def _parse_choice_line(self, line: str, line_no: int, source: str) -> Choice:
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
        return Choice(text=text, target_id=target, condition=condition, line=line_no, source=source)

    def _parse_action_line(self, line: str, line_no: int, source: str) -> Action:
        content = line[1:].strip()
        if content.startswith("set "):
            rest = content[4:].strip()
            if "=" not in rest:
                raise ParseError("Invalid set syntax.")
            var, val = rest.split("=", 1)
            var = self._ensure_valid_var(var)
            return Action(op="set", var=var, value=self._parse_value(val.strip()), line=line_no, source=source)
        if content.startswith("add "):
            rest = content[4:].strip()
            if "+=" not in rest:
                raise ParseError("Invalid add syntax.")
            var, val = rest.split("+=", 1)
            var = self._ensure_valid_var(var)
            return Action(op="add", var=var, value=self._parse_value(val.strip()), line=line_no, source=source)
        m = re.match(r"(\w+)\s*(=|\+=|-=|\*=|/=|//=|%=|\*\*=)\s*(.+)", content)
        if m:
            var, op, val = m.groups()
            var = self._ensure_valid_var(var)
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
            if op == "=":
                try:
                    parsed = self._parse_value(val.strip())
                    return Action(op="set", var=var, value=parsed, line=line_no, source=source)
                except ParseError:
                    return Action(op="expr", var=var, value=val.strip(), line=line_no, source=source)
            return Action(op=op_map[op], var=var, value=self._parse_value(val.strip()), line=line_no, source=source)
        raise ParseError("Unknown action command.")

    def _ensure_valid_var(self, name: str) -> str:
        name = name.strip()
        if not name or "__" in name or name.startswith("_") or name.endswith("_"):
            raise ParseError("Invalid variable name.")
        return name

    def _parse_value(self, token: str) -> Union[int, float, bool, str]:
        t = token.lower()
        if t == "true":
            return True
        if t == "false":
            return False
        if (token.startswith('"') and token.endswith('"')) or (
            token.startswith("'") and token.endswith("'")
        ):
            try:
                return ast.literal_eval(token)
            except Exception:
                raise ParseError(f"Invalid value: {token}")
        try:
            return int(token)
        except ValueError:
            try:
                return float(token)
            except ValueError:
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token):
                    return token
                raise ParseError(f"Invalid value: {token}")
