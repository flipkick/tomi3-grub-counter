@echo off
call pyinstaller --onefile --console extract_grub_counter_from_save.py
call pyinstaller --onefile --console monitor_grub_counter.py
