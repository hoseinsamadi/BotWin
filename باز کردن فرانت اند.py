import locale
import webbrowser
import subprocess
import sys
from pathlib import Path

def open_web_interface():
    html_path = Path(__file__).parent / "index.html"
    if not html_path.exists():
        print(f"خطا: فایل {html_path} یافت نشد.")
        return

    print("در حال باز کردن فرانت‌اند وب در مرورگر...")
    webbrowser.open(f"file:///{html_path.absolute().as_posix()}")

if __name__ == "__main__":
    open_web_interface()