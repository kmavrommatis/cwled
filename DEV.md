
## Manage dependencies with uv

To sync the dependencies:
```bash
uv sync
```

To add a new dependency:
```bash
uv add <package_name>
```

To add a dev dependency:
```bash
uv add --group dev <package_name>
```

## Create a release build

Production releases are automated using GitHub Actions.

Create the public repo (once)
```bash
git remote add public https://github.com/kmavrommatis/cwled.git
```

### Automated Release Process

To trigger an automated production release:
1. Update the version and write your release notes in `NOTES.txt`.
2. Run `make release` with your GitHub Personal Access Token (`GITHUB_PAT`):
   ```bash
   export GITHUB_PAT=your_token_here
   make release
   ```

The Makefile will automatically:
- Read the version from `NOTES.txt`.
- Update internal version numbers in the source files.
- Commit the version update, create a release branch (`v<version>`), tag it, and push both to the public GitHub repository.
- Switch back to `main`.

Once pushed, the **GitHub Actions** workflow (`Build and Release`) will:
- Spin up macOS and Linux runners to compile production bundles.
- Build the macOS DMG installer and Linux tarball.
- Parse `NOTES.txt` to populate the GitHub Release body.
- Create a new draft/published release on GitHub and attach both build artifacts.


## Local Debugging Builds

Local builds are supported **exclusively for debugging purposes**. For production, always use the automated GitHub Actions release workflow.

Ensure dev dependencies are synced:
```bash
uv sync --group dev
```

### Local macOS Debug Build
To build and package the application as a macOS `.app` and `.dmg` locally for debugging:
```bash
make debug-mac
```
This runs PyInstaller, structures the distribution folder, and packages it into `dist/CWLed-Installer.dmg` using `hdiutil`.

### Local Linux Debug Build
To build and package the application as a Linux executable and tarball locally for debugging:
```bash
make debug-linux
```
This runs PyInstaller, sets up a wrapper script (`run.sh`), and creates `dist/CWLed-Linux.tar.gz`.



## Tests to run 

```
cd cwled
uv run ./cwled.py

# Opens the application
```

### Test the Workspace buttons
Click 'Set' and set the workspace. A file dialog should open confirming the new directory.
Click 'Open Workspace' and verify the workspace opens.
Click 'Sort by Name' and 'Sort by Date' and verify the file list is sorted accordingly.
Click 'Rescan' and verify the file list is refreshed.
Click 'Close' and verify the Dialog closes.
Select a file from the list and click 'Open Selected File'.

### Test the Editor buttons
Click 'Create CommandLineTool' and verify the command line editor opens.

Go to App
 add an argument and verify it is added to the command line.
 add an input file and verify it is added to the command line. Type File, with secondary files, of certain format.
 add an output file and verify it is added to the command line. Type File, with secondary files, of certain format.

