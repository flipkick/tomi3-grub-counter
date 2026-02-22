.PHONY: all build build-bin appimage appimage-docker appimage-docker-image \
        appimage-docker-save-gui appimage-docker-monitor-gui \
        ensure-appimage-docker-image \
        collect-appimage-artifacts prep-appdir-save-gui prep-appdir-monitor-gui \
        clean publish
.DEFAULT_GOAL := all

UV := $(shell command -v uv 2>/dev/null)
RUN := $(if $(UV),uv run ,)
APPIMAGE_DOCKER_IMAGE := tomi3-grub-counter-appimage-builder:jammy
APPIMAGE_DOCKERFILE := docker/appimage-builder.Dockerfile
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n1)
OS := $(shell uname -s | tr '[:upper:]' '[:lower:]')
ARCH := $(shell uname -m)
TARGET_SUFFIX := $(VERSION)-$(OS)-$(ARCH)
BIN_NAME_CLI := tomi3-grub-read-save-cli-$(TARGET_SUFFIX)
BIN_NAME_MONITOR := tomi3-grub-monitor-live-cli-$(TARGET_SUFFIX)

all: build-bin appimage

build:
	$(if $(UV),uv build,pip install build && python -m build)

build-bin:
	$(RUN)pyinstaller --onefile --console --name $(BIN_NAME_CLI)     extract_grub_count_from_save.py
	$(RUN)pyinstaller --onefile --console --name $(BIN_NAME_MONITOR) monitor_grub_count.py

appimage: appimage-docker-save-gui appimage-docker-monitor-gui

# kept as alias for backwards compatibility
appimage-docker: appimage-docker-save-gui appimage-docker-monitor-gui

ensure-appimage-docker-image:
	@command -v docker >/dev/null 2>&1 || { \
	  echo "Missing tool: docker"; \
	  echo "Install/start Docker and retry."; \
	  exit 1; \
	}
	@docker image inspect $(APPIMAGE_DOCKER_IMAGE) >/dev/null 2>&1 || \
	  docker build -f $(APPIMAGE_DOCKERFILE) -t $(APPIMAGE_DOCKER_IMAGE) .

appimage-docker-image:
	docker build -f $(APPIMAGE_DOCKERFILE) -t $(APPIMAGE_DOCKER_IMAGE) .

appimage-docker-save-gui: prep-appdir-save-gui ensure-appimage-docker-image
	docker run --rm \
	  --user "$$(id -u):$$(id -g)" \
	  -e HOME=/tmp \
	  -v "$(CURDIR):/workspace" \
	  -w /workspace \
	  $(APPIMAGE_DOCKER_IMAGE) \
	  appimage-builder --recipe AppImageBuilder-save-gui.yml --skip-test
	$(MAKE) collect-appimage-artifacts

appimage-docker-monitor-gui: prep-appdir-monitor-gui ensure-appimage-docker-image
	docker run --rm \
	  --user "$$(id -u):$$(id -g)" \
	  -e HOME=/tmp \
	  -v "$(CURDIR):/workspace" \
	  -w /workspace \
	  $(APPIMAGE_DOCKER_IMAGE) \
	  appimage-builder --recipe AppImageBuilder-monitor.yml --skip-test
	$(MAKE) collect-appimage-artifacts

collect-appimage-artifacts:
	@mkdir -p dist; \
	found=0; \
	for f in ./*.AppImage ./*.AppImage.zsync; do \
	  [ -e "$$f" ] || continue; \
	  mv -f "$$f" dist/; \
	  found=1; \
	done; \
	if [ "$$found" -eq 0 ]; then \
	  echo "No AppImage artifacts found in project root."; \
	  exit 1; \
	fi

prep-appdir-save-gui: resources/tomi3-grub-counter.png
	mkdir -p AppDir-save/usr/share/tomi3-grub-counter \
	         AppDir-save/usr/share/applications \
	         AppDir-save/usr/share/icons/hicolor/256x256/apps
	cp extract_grub_count_from_save_gui.py tomi3_save.py AppDir-save/usr/share/tomi3-grub-counter/
	cp resources/tomi3-grub-counter.png AppDir-save/tomi3-grub-counter.png
	cp resources/tomi3-grub-counter.png AppDir-save/usr/share/icons/hicolor/256x256/apps/tomi3-grub-counter.png
	cp tomi3-grub-read-save-gui.desktop AppDir-save/
	cp tomi3-grub-read-save-gui.desktop AppDir-save/usr/share/applications/
	cp tomi3-grub-read-save-gui.desktop AppDir-save/com.github.flipkick.tomi3grubcounter.desktop
	cp tomi3-grub-read-save-gui.desktop AppDir-save/usr/share/applications/com.github.flipkick.tomi3grubcounter.desktop

prep-appdir-monitor-gui: resources/tomi3-grub-counter.png
	mkdir -p AppDir-monitor/usr/share/tomi3-grub-counter \
	         AppDir-monitor/usr/share/applications \
	         AppDir-monitor/usr/share/icons/hicolor/256x256/apps
	cp monitor_grub_count_gui.py monitor_grub_count.py tomi3_ram.py AppDir-monitor/usr/share/tomi3-grub-counter/
	cp resources/tomi3-grub-counter.png AppDir-monitor/tomi3-grub-counter.png
	cp resources/tomi3-grub-counter.png AppDir-monitor/usr/share/icons/hicolor/256x256/apps/tomi3-grub-counter.png
	cp tomi3-grub-monitor-live.desktop AppDir-monitor/
	cp tomi3-grub-monitor-live.desktop AppDir-monitor/usr/share/applications/
	cp tomi3-grub-monitor-live.desktop AppDir-monitor/com.github.flipkick.tomi3grubmonitor.desktop
	cp tomi3-grub-monitor-live.desktop AppDir-monitor/usr/share/applications/com.github.flipkick.tomi3grubmonitor.desktop

resources/tomi3-grub-counter.png:
	mkdir -p resources
	convert -size 256x256 xc:'#1a1a2e' \
	  -fill '#e94560' -draw 'circle 128,128 128,40' \
	  -fill white -font DejaVu-Sans-Bold -pointsize 52 \
	  -gravity center -annotate 0 'G' \
	  resources/tomi3-grub-counter.png

clean:
	rm -rf build dist AppDir-save AppDir-monitor __pycache__ *.spec *.AppImage
