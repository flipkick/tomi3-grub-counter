@echo off
call pyinstaller --onefile --console extract_grub_count_from_save.py
call pyinstaller --onefile --windowed extract_grub_count_from_save_gui.py
call pyinstaller --onefile --console monitor_grub_count.py
