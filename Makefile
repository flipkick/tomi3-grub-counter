.PHONY: build build-bin clean publish

build:
	pip install build
	python -m build

build-bin:
	pyinstaller --onefile --console extract_grub_count_from_save.py
	pyinstaller --onefile --windowed extract_grub_count_from_save_gui.py
	pyinstaller --onefile --console monitor_grub_count.py


clean:
	rm -rf build dist __pycache__ *.spec
