# Branching Novel Script Grammar

This repository contains a simple text syntax for writing branching visual novels.
Files typically use the `.bnov` extension and are encoded in UTF-8.

## Metadata lines
- `@title: <title>` – story title (`Untitled` if omitted).
- `@start: <branch_id>` – starting branch id (defaults to the first branch).
- `@ending: <text>` – message shown when the story ends with no choices (`The End` by default).
- `@show-disabled: true` – display unavailable choices as disabled buttons.
- `! <var> = <value>` – define an initial variable before any chapter.

## Chapters and branches
- `@chapter <chapter_id>: <title>` – declare a chapter; the title is optional.
- `# <branch_id>: <title>` – begin a branch inside the current chapter; the title is optional.
  Chapter and branch identifiers must be unique across the file.

## Narrative paragraphs and interpolation
Inside a branch, plain text lines form the body. Blank lines separate paragraphs.
Any `${var}` tokens in titles, paragraph text, or choice labels are replaced with
the current value of that variable.

## State actions
Lines beginning with `!` inside a branch modify variables.
Supported operations are:
- `! <var> = <value>` – assignment.
- `! <var> += <value>`, `-=`, `*=`, `/=`, `//=`, `%=` , `**=` – arithmetic updates.
- `! set <var> = <value>` and `! add <var> += <value>` – alternative forms for
  assignment and addition.
Values may be numbers or booleans (`true`/`false`).

## Choices
- `* <text> -> <target_branch_id>` – create a choice leading to another branch.
- `* [<condition>] <text> -> <target_branch_id>` – conditional choice.

### Condition syntax
Conditions are boolean expressions evaluated with the current variables. They
support:
- Variables, numeric literals, and `true`/`false` (case-insensitive).
- Arithmetic: `+ - * / // % **`.
- Comparisons: `== != < <= > >=`.
- Logical operators: `!` (not), `&`/`&&` (and), `|`/`||` (or).

No separate comment syntax is supported; empty lines only serve as paragraph
separators.

## Example
```bnov
@title: Sample Adventure
@start: intro

@chapter intro: Prologue
# intro
You wake up in a dark room.

* Look around -> look
* [key_found] Open the door -> hall
```

## Running the viewer
```
python branching_novel.py path/to/story.bnov
```
