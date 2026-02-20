@echo off
pyinstaller --onefile --console extract_grub_counter_from_save.py
pyinstaller --onefile --console monitor_grub_counter.py
