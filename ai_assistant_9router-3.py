"""
ربات دستیار ویندوز - متصل به 9Router (یا هر endpoint سازگار با OpenAI)
----------------------------------------------------------------------
نصب:
    pip install openai
اجرا:
    python ai_assistant_9router.py
بعد از اجرا روی دکمه‌ی «تنظیمات» بزن و آدرس، کلید و مدل رو وارد کن.
"""

import os
import json
import threading
import datetime
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path

from openai import OpenAI

CONFIG_FILE = Path.home() / ".ai_assistant_config.json"
NOTES_DIR = Path.home() / "AssistantNotes"
NOTES_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG = {
    "base_url": "http://localhost:20128/v1",  # آدرس پیش‌فرض 9Router
    "api_key": "",
    "model": "",
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# فقط برنامه‌های این لیست قابل اجرا هستند (برای امنیت)
APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
}

SYSTEM_PROMPT = (
    "You are a helpful personal assistant running on the user's Windows PC. "
    "Reply in the same language the user writes in (Persian by default). "
    "Use the available tools when the user asks you to do something on the computer. "
    "Be brief and clear."
)


def fn(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


TOOLS = [
    fn("open_app", "Open an allowed Windows app. Options: " + ", ".join(APPS),
       {"name": {"type": "string", "enum": list(APPS)}}, ["name"]),
    fn("open_url", "Open a website in the default browser.",
       {"url": {"type": "string"}}, ["url"]),
    fn("save_note", "Save a text note to the notes folder.",
       {"title": {"type": "string"}, "content": {"type": "string"}}, ["title", "content"]),
    fn("list_notes", "List saved notes."),
    fn("read_note", "Read a saved note by file name.",
       {"filename": {"type": "string"}}, ["filename"]),
    fn("current_time", "Get the current date and time."),
]


def safe_name(text: str) -> str:
    keep = "".join(c for c in text if c.isalnum() or c in " -_").strip()
    return keep[:60] or "note"


def run_tool(name: str, args: dict) -> str:
    try:
        if name == "open_app":
            os.startfile(APPS[args["name"]])
            return f"Opened {args['name']}"
        if name == "open_url":
            url = args["url"]
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            webbrowser.open(url)
            return f"Opened {url}"
        if name == "save_note":
            fname = f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{safe_name(args['title'])}.txt"
            (NOTES_DIR / fname).write_text(args["content"], encoding="utf-8")
            return f"Saved as {fname}"
        if name == "list_notes":
            files = sorted(p.name for p in NOTES_DIR.glob("*.txt"))
            return json.dumps(files, ensure_ascii=False) if files else "No notes yet."
        if name == "read_note":
            path = NOTES_DIR / Path(args["filename"]).name
            return path.read_text(encoding="utf-8")
        if name == "current_time":
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return "Unknown tool"
    except Exception as e:
        return f"Error: {e}"


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, cfg, on_save):
        super().__init__(parent)
        self.title("تنظیمات اتصال")
        self.geometry("460x230")
        self.resizable(False, False)
        self.on_save = on_save
        self.transient(parent)

        frm = tk.Frame(self, padx=12, pady=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        tk.Label(frm, text="Base URL").grid(row=0, column=0, sticky="w", pady=4)
        self.url = tk.Entry(frm)
        self.url.insert(0, cfg["base_url"])
        self.url.grid(row=0, column=1, columnspan=2, sticky="ew")

        tk.Label(frm, text="API Key").grid(row=1, column=0, sticky="w", pady=4)
        self.key = tk.Entry(frm, show="*")
        self.key.insert(0, cfg["api_key"])
        self.key.grid(row=1, column=1, columnspan=2, sticky="ew")

        tk.Label(frm, text="Model").grid(row=2, column=0, sticky="w", pady=4)
        self.model = ttk.Combobox(frm)
        self.model.set(cfg["model"])
        self.model.grid(row=2, column=1, sticky="ew")
        tk.Button(frm, text="دریافت مدل‌ها", command=self.fetch_models).grid(
            row=2, column=2, padx=(6, 0)
        )

        tk.Button(frm, text="ذخیره", width=12, command=self.save).grid(
            row=3, column=0, columnspan=3, pady=(16, 0)
        )

    def fetch_models(self):
        try:
            client = OpenAI(
                base_url=self.url.get().strip(),
                api_key=self.key.get().strip() or "sk-local",
                timeout=15,
            )
            ids = sorted(m.id for m in client.models.list().data)
            self.model["values"] = ids
            if ids and not self.model.get():
                self.model.set(ids[0])
            messagebox.showinfo("موفق", f"{len(ids)} مدل پیدا شد.", parent=self)
        except Exception as e:
            messagebox.showerror("خطا", str(e), parent=self)

    def save(self):
        self.on_save({
            "base_url": self.url.get().strip(),
            "api_key": self.key.get().strip(),
            "model": self.model.get().strip(),
        })
        self.destroy()


class AssistantApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("دستیار هوش مصنوعی (9Router)")
        root.geometry("660x580")

        self.cfg = load_config()
        self.client = self.make_client()
        self.history = []

        top = tk.Frame(root)
        top.pack(fill=tk.X, padx=8, pady=(8, 0))
        self.status = tk.Label(top, anchor="w", fg="#555")
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(top, text="تنظیمات", command=self.open_settings).pack(side=tk.RIGHT)
        tk.Button(top, text="پاک کردن چت", command=self.clear_chat).pack(side=tk.RIGHT, padx=6)

        self.chat = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, state=tk.DISABLED, font=("Segoe UI", 11)
        )
        self.chat.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        bottom = tk.Frame(root)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.entry = tk.Entry(bottom, font=("Segoe UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.send())
        self.btn = tk.Button(bottom, text="ارسال", command=self.send, width=10)
        self.btn.pack(side=tk.LEFT, padx=(6, 0))
        self.entry.focus()

        self.refresh_status()
        self.append("دستیار", "سلام! چه کاری می‌تونم برات انجام بدم؟")
        if not self.cfg["model"]:
            self.append("⚙️", "اول از دکمه‌ی «تنظیمات» مدل رو انتخاب کن.")

    def make_client(self):
        return OpenAI(
            base_url=self.cfg["base_url"],
            api_key=self.cfg["api_key"] or "sk-local",
            timeout=120,
        )

    def refresh_status(self):
        self.status.config(text=f"{self.cfg['base_url']}  |  مدل: {self.cfg['model'] or '—'}")

    def open_settings(self):
        SettingsDialog(self.root, self.cfg, self.apply_settings)

    def apply_settings(self, cfg):
        self.cfg = cfg
        save_config(cfg)
        self.client = self.make_client()
        self.refresh_status()
        self.append("⚙️", "تنظیمات ذخیره شد.")

    def clear_chat(self):
        self.history.clear()
        self.chat.config(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.config(state=tk.DISABLED)

    def append(self, who: str, text: str):
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{who}: {text}\n\n")
        self.chat.config(state=tk.DISABLED)
        self.chat.see(tk.END)

    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        if not self.cfg["model"]:
            self.open_settings()
            return
        self.entry.delete(0, tk.END)
        self.append("شما", text)
        self.history.append({"role": "user", "content": text})
        self.btn.config(state=tk.DISABLED)
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            while True:
                resp = self.client.chat.completions.create(
                    model=self.cfg["model"],
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}] + self.history,
                    tools=TOOLS,
                )
                msg = resp.choices[0].message

                if not msg.tool_calls:
                    self.history.append({"role": "assistant", "content": msg.content or ""})
                    self.root.after(0, self.append, "دستیار", msg.content or "(بدون پاسخ)")
                    break

                self.history.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    out = run_tool(tc.function.name, args)
                    self.root.after(0, self.append, "⚙️", f"{tc.function.name}: {out[:120]}")
                    self.history.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": out}
                    )
        except Exception as e:
            self.root.after(0, self.append, "خطا", str(e))
        finally:
            self.root.after(0, lambda: self.btn.config(state=tk.NORMAL))


if __name__ == "__main__":
    root = tk.Tk()
    AssistantApp(root)
    root.mainloop()
