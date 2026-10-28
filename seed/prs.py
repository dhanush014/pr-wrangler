"""The 15 seeded PRs. Each one is a small edit against main (or another PR's branch).

Kept outside the demo repo on purpose: the agents must not be able to read the answers.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent / "todo-app"


# ---------- edit helpers ----------

def edit(path, old, new):
    p = REPO / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected 1 match, found {count}:\n{old}")
    p.write_text(text.replace(old, new))


def append(path, text):
    p = REPO / path
    p.write_text(p.read_text().rstrip("\n") + "\n" + text)


def set_dep(name, version):
    p = REPO / "package.json"
    pkg = json.loads(p.read_text())
    pkg["dependencies"][name] = version
    p.write_text(json.dumps(pkg, indent=2) + "\n")


# ---------- the PRs (order = PR number on a fresh repo) ----------

def pr01_due_dates():
    edit("index.html",
         '        <input id="new-todo-input" type="text" placeholder="What needs to be doen?" />\n',
         '        <input id="new-todo-input" type="text" placeholder="What needs to be doen?" />\n'
         '        <input id="due-input" type="date" aria-label="Due date" />\n')
    edit("app.js",
         'import { format } from "date-fns";',
         'import { format, isBefore, parseISO, startOfToday } from "date-fns";')
    edit("app.js",
         'const list = document.getElementById("todo-list");',
         'const list = document.getElementById("todo-list");\n'
         'const dueInput = document.getElementById("due-input");')
    edit("app.js",
         '  todos.push({ id: Date.now(), title, done: false, createdAt: Date.now() });\n'
         '  input.value = "";\n',
         '  const due = dueInput.value || null;\n'
         '  todos.push({ id: Date.now(), title, done: false, createdAt: Date.now(), due });\n'
         '  input.value = "";\n'
         '  dueInput.value = "";\n')
    edit("app.js",
         '      <span class="meta">Added ${format(todo.createdAt, "MMM d")}</span>\n',
         '      <span class="meta">Added ${format(todo.createdAt, "MMM d")}</span>\n'
         '      <span class="due"></span>\n')
    edit("app.js",
         '    li.querySelector(".title").textContent = todo.title;\n',
         '    li.querySelector(".title").textContent = todo.title;\n'
         '    if (todo.due) {\n'
         '      const overdue = !todo.done && isBefore(parseISO(todo.due), startOfToday());\n'
         '      const badge = li.querySelector(".due");\n'
         '      badge.textContent = `Due ${format(parseISO(todo.due), "MMM d")}`;\n'
         '      badge.classList.add(overdue ? "overdue" : "upcoming");\n'
         '    }\n')
    append("style.css", """
/* ---------- Due dates ---------- */

.new-todo #due-input {
  flex: 0 0 auto;
  width: 150px;
  padding: 10px 8px;
  font-size: 14px;
  font-family: inherit;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.new-todo #due-input:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.new-todo #due-input::-webkit-calendar-picker-indicator {
  cursor: pointer;
  opacity: 0.6;
}

.new-todo #due-input::-webkit-calendar-picker-indicator:hover {
  opacity: 1;
}

.todo .due {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  border-radius: 999px;
}

.todo .due:empty {
  display: none;
}

.todo .due.upcoming {
  padding: 4px 8px;
  color: #1e40af;
  background: #dbeafe;
}

.todo .due.upcoming::before {
  content: "📅";
  font-size: 11px;
}

.todo .due.overdue {
  padding: 4px 8px;
  color: #991b1b;
  background: #fee2e2;
}

.todo .due.overdue::before {
  content: "⏰";
  font-size: 11px;
}

.todo.done .due {
  opacity: 0.5;
}

.todo.done .due.overdue {
  color: var(--muted);
  background: var(--bg);
}

@media (max-width: 480px) {
  .new-todo {
    flex-wrap: wrap;
  }

  .new-todo #due-input {
    flex: 1 1 100%;
    width: auto;
    order: 2;
  }

  .new-todo button {
    order: 3;
    flex: 1 1 100%;
  }

  .todo .due {
    font-size: 11px;
  }
}
""")


def pr02_todo_cards():
    edit("app.js",
         '  if (!confirm("Delete this to-do?")) return;\n', '')
    edit("app.js",
         '    li.className = todo.done ? "todo done" : "todo";',
         '    li.className = todo.done ? "todo-card done" : "todo-card";')
    edit("style.css", """#todo-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.todo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.todo.done .title {
  text-decoration: line-through;
  color: var(--muted);
}

.todo .title {
  flex: 1;
}

.todo .meta {
  font-size: 12px;
  color: var(--muted);
}

.todo .delete {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 18px;
  cursor: pointer;
}
""", """#todo-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.todo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: #ffffff;
  border: 1px solid #eeeeee;
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}

.todo-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.todo-card input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--accent);
  cursor: pointer;
}

.todo-card .title {
  flex: 1;
  font-size: 15px;
  line-height: 1.4;
}

.todo-card.done {
  background: #fafafa;
  box-shadow: none;
}

.todo-card.done .title {
  text-decoration: line-through;
  color: var(--muted);
}

.todo-card .meta {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.todo-card .delete {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--muted);
  font-size: 18px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease;
}

.todo-card:hover .delete {
  opacity: 1;
}

.todo-card .delete:hover {
  background: #fee2e2;
  color: #b91c1c;
}
""")


def pr03_clear_completed():
    edit("index.html",
         '      <ul id="todo-list"></ul>\n',
         '      <div class="toolbar">\n'
         '        <button id="clear-completed">Clear completed</button>\n'
         '      </div>\n\n'
         '      <ul id="todo-list"></ul>\n')
    edit("app.js",
         'const list = document.getElementById("todo-list");',
         'const list = document.getElementById("todo-list");\n'
         'const clearButton = document.getElementById("clear-completed");')
    edit("app.js",
         'function render() {',
         'function clearCompleted() {\n'
         '  todos = todos.filter((t) => t.done);\n'
         '  save();\n'
         '  render();\n'
         '}\n\n'
         'function render() {')
    edit("app.js",
         'addButton.addEventListener("click", addTodo);',
         'addButton.addEventListener("click", addTodo);\n'
         'clearButton.addEventListener("click", clearCompleted);')
    append("style.css", """
.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

#clear-completed {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
}

#clear-completed:hover {
  color: var(--text);
  text-decoration: underline;
}
""")


def pr04_dark_mode():
    edit("style.css", '  --accent: #2563eb;\n',
         '  --accent: #3b82f6;\n  --on-accent: #ffffff;\n')
    edit("style.css",
         '  background: var(--accent);\n  color: white;\n',
         '  background: var(--accent);\n  color: var(--on-accent);\n')
    edit("style.css",
         '  background: var(--surface);\n  border-bottom: 1px solid var(--border);\n}',
         '  background: var(--surface);\n  border-bottom: 1px solid var(--border);\n'
         '  transition: background 0.2s ease, color 0.2s ease;\n}')
    edit("style.css", """:root {
  --bg: #f5f5f5;""", """@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111318;
    --surface: #1b1e24;
    --text: #e8e8e8;
    --muted: #8b9099;
    --border: #2c3038;
    --accent: #60a5fa;
    --on-accent: #0b1220;
  }

  .new-todo input {
    background: var(--surface);
    color: var(--text);
  }
}

:root {
  --bg: #f5f5f5;""")


def pr05_purple_accent():
    edit("style.css", '  --accent: #2563eb;\n', '  --accent: #7c3aed;\n')


def pr06_filter_tabs():
    edit("index.html",
         '      <ul id="todo-list"></ul>\n',
         '      <ul id="todo-list"></ul>\n\n'
         '      <footer class="footer">\n'
         '        <div class="filters">\n'
         '          <button data-filter="all" class="active">All</button>\n'
         '          <button data-filter="active">Active</button>\n'
         '          <button data-filter="done">Done</button>\n'
         '        </div>\n'
         '      </footer>\n')
    edit("app.js",
         'let todos = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");',
         'let todos = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");\n'
         'let filter = "all";')
    edit("app.js",
         '  for (const todo of todos) {',
         '  const visible = todos.filter((t) =>\n'
         '    filter === "all" ? true : filter === "done" ? t.done : !t.done\n'
         '  );\n'
         '  for (const todo of visible) {')
    edit("app.js",
         'addButton.addEventListener("click", addTodo);',
         'addButton.addEventListener("click", addTodo);\n\n'
         'for (const button of document.querySelectorAll(".filters button")) {\n'
         '  button.addEventListener("click", () => {\n'
         '    filter = button.dataset.filter;\n'
         '    document.querySelector(".filters .active").classList.remove("active");\n'
         '    button.classList.add("active");\n'
         '    render();\n'
         '  });\n'
         '}')
    append("style.css", """
.footer {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.filters {
  display: flex;
  gap: 4px;
}

.filters button {
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  color: var(--muted);
  cursor: pointer;
}

.filters button.active {
  border-color: var(--border);
  color: var(--text);
}
""")


def pr07_items_left():
    edit("index.html",
         '      <ul id="todo-list"></ul>\n',
         '      <ul id="todo-list"></ul>\n\n'
         '      <footer class="footer">\n'
         '        <span id="count"></span>\n'
         '      </footer>\n')
    edit("app.js",
         'const list = document.getElementById("todo-list");',
         'const list = document.getElementById("todo-list");\n'
         'const count = document.getElementById("count");')
    edit("app.js",
         '    list.appendChild(li);\n  }\n}',
         '    list.appendChild(li);\n  }\n'
         '  const left = todos.filter((t) => !t.done).length;\n'
         '  count.textContent = `${left} ${left === 1 ? "item" : "items"} left`;\n}')
    append("style.css", """
.footer {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 13px;
  color: var(--muted);
}
""")


def pr08_placeholder_typo():
    edit("index.html", 'What needs to be doen?', 'What needs to be done?')


def pr09_bigger_checkboxes():
    append("style.css", """
@media (max-width: 600px) {
  #todo-list input[type="checkbox"] {
    width: 22px;
    height: 22px;
  }
}
""")


def pr10_drag_reorder():
    # Stacked on PR #2: uses the .todo-card markup that PR introduces.
    edit("app.js",
         '    li.className = todo.done ? "todo-card done" : "todo-card";',
         '    li.className = todo.done ? "todo-card done" : "todo-card";\n'
         '    li.draggable = true;\n'
         '    li.dataset.id = todo.id;\n'
         '    li.addEventListener("dragstart", () => li.classList.add("dragging"));\n'
         '    li.addEventListener("dragend", () => li.classList.remove("dragging"));\n'
         '    li.addEventListener("dragover", (e) => e.preventDefault());\n'
         '    li.addEventListener("drop", () => moveTodo(Number(list.querySelector(".dragging").dataset.id), todo.id));')
    edit("app.js",
         'function render() {',
         'function moveTodo(fromId, toId) {\n'
         '  const from = todos.findIndex((t) => t.id === fromId);\n'
         '  const to = todos.findIndex((t) => t.id === toId);\n'
         '  const [moved] = todos.splice(from, 1);\n'
         '  todos.splice(to, 0, moved);\n'
         '  save();\n'
         '  render();\n'
         '}\n\n'
         'function render() {')
    append("style.css", """
.todo-card[draggable="true"] {
  cursor: grab;
}

.todo-card.dragging {
  opacity: 0.5;
  cursor: grabbing;
}
""")


def pr11_empty_state():
    set_dep("canvas-confetti", "1.6.0")
    edit("app.js",
         'import { format } from "date-fns";',
         'import { format } from "date-fns";\nimport confetti from "canvas-confetti";')
    edit("app.js",
         '  todos = todos.filter((t) => t.id !== id);\n  save();\n  render();\n',
         '  todos = todos.filter((t) => t.id !== id);\n  save();\n  render();\n'
         '  if (todos.length === 0) confetti({ particleCount: 60, spread: 50 });\n')
    edit("app.js",
         '  list.innerHTML = "";\n',
         '  list.innerHTML = "";\n'
         '  if (todos.length === 0) {\n'
         '    list.innerHTML = `<li class="empty">Nothing to do 🎉</li>`;\n'
         '    return;\n'
         '  }\n')
    append("style.css", """
.empty {
  padding: 32px 0;
  text-align: center;
  color: var(--muted);
}
""")


def pr12_enter_to_add():
    edit("app.js",
         'addButton.addEventListener("click", addTodo);',
         'addButton.addEventListener("click", addTodo);\n'
         'input.addEventListener("keydown", (e) => {\n'
         '  if (e.key === "Enter") addTodo();\n'
         '});')


def pr13_relative_time():
    set_dep("moment", "^2.30.1")
    edit("app.js",
         'import { format } from "date-fns";',
         'import moment from "moment";')
    edit("app.js",
         '      <span class="meta">Added ${format(todo.createdAt, "MMM d")}</span>\n',
         '      <span class="meta">Added ${moment(todo.createdAt).fromNow()}</span>\n')


def pr14_search():
    set_dep("lodash", "4.17.15")
    edit("index.html",
         '      <h1>Tiny Todo</h1>\n',
         '      <h1>Tiny Todo</h1>\n\n'
         '      <input id="search" type="search" placeholder="Search to-dos" />\n')
    edit("app.js",
         'import { format } from "date-fns";',
         'import { format } from "date-fns";\nimport { debounce } from "lodash";')
    edit("app.js",
         'let todos = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");',
         'let todos = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");\n'
         'let query = "";')
    edit("app.js",
         '  for (const todo of todos) {',
         '  for (const todo of todos.filter((t) => t.title.toLowerCase().includes(query))) {')
    edit("app.js",
         'addButton.addEventListener("click", addTodo);',
         'addButton.addEventListener("click", addTodo);\n'
         'document.getElementById("search").addEventListener(\n'
         '  "input",\n'
         '  debounce((e) => {\n'
         '    query = e.target.value.trim().toLowerCase();\n'
         '    render();\n'
         '  }, 200)\n'
         ');')
    append("style.css", """
#search {
  width: 100%;
  margin-bottom: 12px;
  padding: 8px 12px;
  font-size: 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
""")


def pr15_confetti():
    set_dep("canvas-confetti", "^1.9.3")
    edit("app.js",
         'import { format } from "date-fns";',
         'import { format } from "date-fns";\nimport confetti from "canvas-confetti";')
    edit("app.js",
         '  todo.done = !todo.done;\n  save();\n  render();\n',
         '  todo.done = !todo.done;\n  save();\n  render();\n'
         '  if (todos.length > 0 && todos.every((t) => t.done)) {\n'
         '    confetti({ particleCount: 150, spread: 80, origin: { y: 0.7 } });\n'
         '  }\n')


# author = one of the 7 teammates (shown on the commit; the PR itself is opened by the repo owner)
PRS = [
    dict(n=1, branch="feat/due-dates", author="Priya", apply=pr01_due_dates,
         title="Add due dates to to-dos",
         body="## Summary\n- Adds a date picker next to the input\n- Shows a due badge on each to-do, red when overdue\n- Mobile layout for the new input"),
    dict(n=2, branch="ui/todo-cards", author="Marcus", apply=pr02_todo_cards,
         title="Restyle to-do items as cards",
         body="## Summary\n- To-do items are now cards with rounded corners, shadow and hover lift\n- Delete button only shows on hover\n- General cleanup"),
    dict(n=3, branch="feat/clear-completed", author="Aiko", apply=pr03_clear_completed,
         title="Add 'Clear completed' button",
         body="## Summary\n- Adds a small 'Clear completed' button above the list to remove finished to-dos in one click"),
    dict(n=4, branch="ui/dark-mode", author="Diego", apply=pr04_dark_mode,
         title="Dark mode",
         body="## Summary\n- Follows the system theme via prefers-color-scheme\n- Slightly brighter accent for better contrast in both themes"),
    dict(n=5, branch="ui/purple-accent", author="Lena", apply=pr05_purple_accent,
         title="Change accent color to purple",
         body="Brand refresh: accent color is now purple."),
    dict(n=6, branch="feat/filter-tabs", author="Sam", apply=pr06_filter_tabs,
         title="Filter tabs: All / Active / Done",
         body="## Summary\n- Adds All / Active / Done tabs under the list"),
    dict(n=7, branch="feat/items-left", author="Omar", apply=pr07_items_left,
         title="Show 'N items left' counter",
         body="## Summary\n- Footer shows how many to-dos are left"),
    dict(n=8, branch="fix/placeholder-typo", author="Aiko", apply=pr08_placeholder_typo,
         title="Fix typo in input placeholder",
         body="doen -> done"),
    dict(n=9, branch="ui/mobile-checkboxes", author="Lena", apply=pr09_bigger_checkboxes,
         title="Bigger checkboxes on mobile",
         body="Checkboxes were hard to tap on phones. Bumps them to 22px under 600px width."),
    dict(n=10, branch="feat/drag-reorder", base="ui/todo-cards", author="Marcus", apply=pr10_drag_reorder,
         title="Drag to reorder to-dos",
         body="## Summary\n- Drag a card to reorder the list\n- Order is saved"),
    dict(n=11, branch="ui/empty-state", author="Sam", apply=pr11_empty_state,
         title="Empty state message",
         body="## Summary\n- Shows 'Nothing to do 🎉' when the list is empty\n- Small celebration when you delete the last to-do"),
    dict(n=12, branch="feat/enter-to-add", author="Omar", apply=pr12_enter_to_add,
         title="Press Enter to add a to-do",
         body="You can now hit Enter instead of clicking Add."),
    dict(n=13, branch="ui/relative-time", author="Diego", apply=pr13_relative_time,
         title="Show relative time ('added 3 days ago')",
         body="## Summary\n- 'Added Oct 15' becomes 'Added 3 days ago'"),
    dict(n=14, branch="feat/search", author="Priya", apply=pr14_search,
         title="Search box for to-dos",
         body="## Summary\n- Adds a search box above the list\n- Debounced so it doesn't re-render on every keystroke"),
    dict(n=15, branch="feat/confetti", author="Lena", apply=pr15_confetti,
         title="Confetti when everything is done 🎉",
         body="## Summary\n- Confetti burst when the last to-do gets checked off"),
]
