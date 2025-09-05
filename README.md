# Branching Novel Script Syntax

Branching Novel Script is a plain-text format for writing branching visual
novels. Scripts usually use the `.bnov` extension and must be encoded in UTF-8.

## Metadata lines

Directives at the top of the file configure global story settings:

- `@title: <title>` – story title (`Untitled` if omitted).
- `@start: <branch_id>` – starting branch id (defaults to the first branch in the file).
- `@ending: <text>` – message shown when the story ends with no choices (`The End` by default).
- `@show-disabled: true` – display unavailable choices as disabled buttons.
- `! <var> = <value or expression>` – define an initial variable before any chapter. Expressions may reference previously defined variables.

## Chapters and branches

- `@chapter <chapter_id>: <title>` – declare a chapter; the title is optional.
- `# <branch_id>: <title>` – begin a branch inside the current chapter; the title is optional.

Chapter and branch identifiers must be unique across the file.

## Narrative paragraphs and interpolation

Inside a branch, plain text lines form the body. Blank lines separate
paragraphs. Any `__var__` tokens in titles, paragraph text, or choice labels are
replaced with the current value of that variable; if the variable is undefined
the placeholder remains unchanged.

Variable names may contain letters, digits and underscores but cannot start or
end with `_` or contain `__`.

## State actions

Lines beginning with `!` inside a branch modify variables. Supported forms are

- `! <var> = <value or expression>` – assignment. If the right-hand side is not a literal it is evaluated as an expression.
- `! <var> += <value>`, `-=`, `*=`, `/=`, `//=`, `%=` , `**=` – arithmetic updates.
- `! set <var> = <value>` and `! add <var> += <value>` – explicit assignment and addition.

Values may be numbers, strings, booleans (`true`/`false`) or other variable names.
When used with arithmetic operators booleans are treated as `0` or `1`.
Undefined variables evaluate to `0`.

## Choices

- `* <text> -> <target_branch_id>` – create a choice leading to another branch.
- `* [<condition>] <text> -> <target_branch_id>` – conditional choice.

## Condition and expression syntax

Conditions and expressions support:

- Variables, numeric literals, quoted strings, and `true`/`false` (case-insensitive).
- Arithmetic: `+ - * / // % **` and unary `-`.
- Comparisons: `== != < <= > >=`.
- Logical operators: `!` (not), `&`/`&&` (and), `|`/`||` (or).
- Parentheses for grouping.

No separate comment syntax is supported; empty lines only serve as paragraph
separators.

## Example

```bnov
@title: Sample Adventure
@start: intro
@show-disabled: true
! coins = 5

@chapter intro: Prologue
# intro
You wake up with __coins__ coins.
! coins += 3

* Search the room -> search
* [coins >= 10] Buy a snack -> shop
```

## Running the viewer

```
python branching_novel.py path/to/story.bnov
```

## Building installers

Use `editor_installer.iss` to build the editor installer and `game_installer.iss` for the game. Each wrapper defines its own payload and only writes the language file it needs, while sharing common logic from `installer.iss`.
