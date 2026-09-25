.PHONY: all clean build prepare-dist dmg prepare-icons help debug-mac debug-linux linux-build linux-dist linux-tar release

# Variables
APP_NAME = CWLed
DIST_FOLDER = CWL editor
DMG_NAME = CWLed-Installer.dmg
LINUX_DIST_FOLDER = cwled-linux
TAR_NAME = CWLed-Linux.tar.gz

# Detect OS
UNAME_S := $(shell uname -s)

# Default target shows help to encourage explicit debug targets
all: help

# Local debugging target for macOS
debug-mac: build prepare-dist dmg
	@echo "Local macOS debug build completed: dist/$(DMG_NAME)"

# Local debugging target for Linux
debug-linux: linux-build linux-dist linux-tar
	@echo "Local Linux debug build completed: dist/$(TAR_NAME)"

# Build the application using PyInstaller
build: update-version
	@echo "Building $(APP_NAME) application..."
	rm -rf dist/ build/
	uv run pyinstaller --noconfirm --clean cwled.spec

# Prepare the distribution folder
prepare-dist:
	@echo "Preparing distribution folder..."
	cd dist && \
	mkdir -p '$(DIST_FOLDER)' && \
	mv $(APP_NAME).app '$(DIST_FOLDER)/$(APP_NAME).app' && \
	ln -s /Applications '$(DIST_FOLDER)/Applications'

# Create DMG file using hdiutil
dmg:
	@echo "Creating DMG file..."
	cd dist && \
	hdiutil create -volname "$(APP_NAME)" -srcfolder '$(DIST_FOLDER)' -ov -format UDZO $(DMG_NAME)
	@echo "DMG file created: dist/$(DMG_NAME)"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf dist/ build/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

# Build without creating DMG
build-only: build prepare-dist

# ============= Icon Preparation =============

# Prepare icons for the application
prepare-icons:
	@echo "Preparing application icons..."
	mkdir -p resources/cwled.iconset
	cp resources/icons/cwled.png resources/cwled.png
	cd resources && \
	sips -z 16 16     cwled.png --out cwled.iconset/icon_16x16.png && \
	sips -z 32 32     cwled.png --out cwled.iconset/icon_16x16@2x.png && \
	sips -z 32 32     cwled.png --out cwled.iconset/icon_32x32.png && \
	sips -z 64 64     cwled.png --out cwled.iconset/icon_32x32@2x.png && \
	sips -z 128 128   cwled.png --out cwled.iconset/icon_128x128.png && \
	sips -z 256 256   cwled.png --out cwled.iconset/icon_128x128@2x.png && \
	sips -z 256 256   cwled.png --out cwled.iconset/icon_256x256.png && \
	sips -z 512 512   cwled.png --out cwled.iconset/icon_256x256@2x.png && \
	sips -z 512 512   cwled.png --out cwled.iconset/icon_512x512.png && \
	cp cwled.png cwled.iconset/icon_512x512@2x.png && \
	iconutil --convert icns --output icons/cwled.icns cwled.iconset && \
	rm -R cwled.iconset
	@echo "Icons prepared successfully!"

# ============= Linux Targets =============

# Build for Linux
linux: linux-build linux-dist linux-tar

# Build the Linux executable using PyInstaller
linux-build:
	@echo "Building $(APP_NAME) for Linux..."
	rm -rf dist/ build/
	uv run pyinstaller --noconfirm --clean cwled.spec

# Prepare Linux distribution folder
linux-dist:
	@echo "Preparing Linux distribution..."
	cd dist && \
	mkdir -p '$(LINUX_DIST_FOLDER)' && \
	if [ -d "$(APP_NAME)" ]; then \
		cp -r $(APP_NAME)/* '$(LINUX_DIST_FOLDER)/'; \
	elif [ -f "$(APP_NAME)" ]; then \
		cp $(APP_NAME) '$(LINUX_DIST_FOLDER)/'; \
	fi && \
	echo '#!/bin/bash' > '$(LINUX_DIST_FOLDER)/run.sh' && \
	echo 'cd "$$(dirname "$$0")"' >> '$(LINUX_DIST_FOLDER)/run.sh' && \
	echo './$(APP_NAME)' >> '$(LINUX_DIST_FOLDER)/run.sh' && \
	chmod +x '$(LINUX_DIST_FOLDER)/run.sh'

# Create tarball for Linux
linux-tar:
	@echo "Creating tarball for Linux..."
	cd dist && \
	tar -czf $(TAR_NAME) '$(LINUX_DIST_FOLDER)'
	@echo "Tarball created: dist/$(TAR_NAME)"

# Build Linux without creating tarball
linux-build-only: linux-build linux-dist

# ============= Version Management =============

# Update version in cwled/__init__.py from NOTES.txt
update-version:
	$(eval VERSION := $(shell awk -F ":" '{print $$2}' NOTES.txt | tr -d ' '))
	@echo "Updating version to $(VERSION)"
	@echo '"""CWLed - Common Workflow Language Editor"""' > cwled/__init__.py
	@echo '' > cwled/version.py
	@echo '__version__ = "$(VERSION)"' >> cwled/version.py
	@echo "Version updated to $(VERSION) in cwled/version.py"

# ============= Release =============

# Create a release (requires GITHUB_PAT environment variable)
release: update-version
	@echo "Creating release tags and pushing to public remote..."
	@if [ -z "$$GITHUB_PAT" ]; then \
		echo "Error: GITHUB_PAT environment variable not set"; \
		exit 1; \
	fi
	$(eval RELEASE_VERSION := $(shell awk -F ":" '{print $$2}' NOTES.txt | tr -d ' '))
	@echo "Release version: $(RELEASE_VERSION)"
	git checkout main && git pull
	git checkout --orphan v$(RELEASE_VERSION)
	git add . && git commit -m "Release $(RELEASE_VERSION)"
	git push -f public v$(RELEASE_VERSION):main
	git tag -a v$(RELEASE_VERSION) -m "Release $(RELEASE_VERSION)"
	git push public tag v$(RELEASE_VERSION)
	git checkout main
	git branch -D v$(RELEASE_VERSION)
	@echo "Tag v$(RELEASE_VERSION) created and pushed successfully! GitHub Actions will now build and create the release."

# ============= Help =============

# Help target
help:
	@echo "Available targets:"
	@echo ""
	@echo "Local Debugging targets:"
	@echo "  debug-mac        - Build macOS app, prepare distribution, and create DMG (for debugging)"
	@echo "  debug-linux      - Build Linux executable, prepare distribution, and create tarball (for debugging)"
	@echo "  clean            - Remove build artifacts and cache files"
	@echo ""
	@echo "Release targets:"
	@echo "  release          - Update version, tag release branch, and push to trigger GitHub Action build"
	@echo ""
	@echo "Detailed macOS targets (used by debug-mac):"
	@echo "  build            - Build the macOS application using PyInstaller"
	@echo "  prepare-dist     - Prepare the macOS distribution folder structure"
	@echo "  dmg              - Create DMG file from distribution folder"
	@echo "  build-only       - Build and prepare distribution without creating DMG"
	@echo ""
	@echo "Detailed Linux targets (used by debug-linux):"
	@echo "  linux-build      - Build the Linux executable using PyInstaller"
	@echo "  linux-dist       - Prepare the Linux distribution folder"
	@echo "  linux-tar        - Create tarball from Linux distribution"
	@echo "  linux-build-only - Build and prepare Linux distribution without creating tarball"
	@echo ""
	@echo "Utility targets:"
	@echo "  prepare-icons    - Generate application icon set from source PNG"
	@echo "  update-version   - Sync version from NOTES.txt to cwled/__init__.py and cwled/version.py"
	@echo "  help             - Show this help message"
