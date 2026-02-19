EXE = dist/read_grub_counter.exe

.PHONY: build clean

build:
	pyinstaller --onefile --console read_grub_counter.py

clean:
	rm -rf build dist __pycache__ *.spec
