"""Build script for LA 2028 Schedule Builder .exe"""
import subprocess
import sys

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",
    "--windowed",
    "--name", "LA2028ScheduleBuilder",
    "--add-data", "LA 2028 Session Table - Shareable.xlsx;.",
    "--hidden-import", "customtkinter",
    "--hidden-import", "tkintermapview",
    "--hidden-import", "PIL",
    "--hidden-import", "openpyxl",
    "--hidden-import", "pandas",
    "--collect-all", "customtkinter",
    "--collect-all", "tkintermapview",
    "--noconfirm",
    "app.py",
]

print("Building .exe...")
print(" ".join(cmd))
subprocess.run(cmd, check=True)
print("\nDone! .exe is in dist/LA2028ScheduleBuilder/")
