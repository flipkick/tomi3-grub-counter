EXES = dist/extract_grub_counter_from_save.exe dist/monitor_grub_counter.exe

.PHONY: build build-exe clean publish

build:
	pip install build
	python -m build

build-exe:
	pyinstaller --onefile --console extract_grub_counter_from_save.py
	pyinstaller --onefile --console monitor_grub_counter.py


clean:
	rm -rf build dist __pycache__ *.spec
