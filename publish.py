"""
VladgeMinifier Automated Release and Publishing Script.
Builds the app, packages it as a zip, and publishes it to GitHub.
"""

from __future__ import annotations
import os
import sys
import subprocess
import shutil
import zipfile
from pathlib import Path

# Add project root to path
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

# Reconfigure stdout/stderr to handle emojis in standard Windows terminals
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from src.version import __version__ as APP_VERSION

GITHUB_REPO = "rjwolfe44/Stormworks-Minifier-Vladge"

def run_cmd(args: list[str], shell: bool = False):
    print(f"Running: {' '.join(args)}")
    res = subprocess.run(args, shell=shell, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"Error executing command: {res.stderr}")
        sys.exit(res.returncode)
    print(res.stdout)

def run_gh_cmd(args: list[str]):
    print(f"Running: {' '.join(args)}")
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"\n[!] GitHub CLI action failed: {res.stderr.strip()}")
        print("    Your release could not be published automatically to GitHub.")
        print("    Please ensure you are logged in via 'gh auth login' and the repository exists.")
    else:
        print(res.stdout)

def main():
    print(f"=== VladgeMinifier Release Publisher (v{APP_VERSION}) ===")
    
    # 1. Run tests to ensure everything passes
    print("\n[1/4] Running test suite...")
    res = subprocess.run(["python", "-m", "pytest"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"ERROR: Tests failed! Please fix all tests before releasing:\n{res.stdout}\n{res.stderr}")
        sys.exit(1)
    print("      All tests passed successfully.")

    # 2. Run build.bat to compile the executables
    print("\n[2/4] Building executables via build.bat...")
    if sys.platform == "win32":
        run_cmd(["build.bat"], shell=True)
    else:
        print("ERROR: Building is only supported on Windows.")
        sys.exit(1)

    # 3. Create zip distribution from _export/VladgeMinifier
    print("\n[3/4] Creating zip distribution archive...")
    export_dir = _HERE / "_export" / "VladgeMinifier"
    if not export_dir.exists():
        print(f"ERROR: Export directory not found at {export_dir}!")
        sys.exit(1)

    dist_dir = _HERE / "dist"
    dist_dir.mkdir(exist_ok=True)
    zip_path = dist_dir / f"VladgeMinifier-v{APP_VERSION}.zip"
    
    # Zip up the entire folder structure
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in export_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(export_dir.parent)
                zip_file.write(file_path, rel_path)

    print(f"      Zip file created: {zip_path.name} ({zip_path.stat().st_size / 1024 / 1024:.2f} MB)")

    # 4. Check for GitHub CLI and publish release
    print("\n[4/4] Publishing release to GitHub...")
    # Check if gh CLI is available
    gh_path = shutil.which("gh")
    if gh_path:
        print("      GitHub CLI ('gh') detected. Creating release automatically...")
        tag = f"v{APP_VERSION}"
        title = f"VladgeMinifier {tag}"
        notes = f"Release of VladgeMinifier {tag}. Merges advanced optimization levels to Ultimate and implements automatic updates check."
        
        # Check if release/tag already exists on GitHub
        print("      Querying GitHub for existing release...")
        gh_check = subprocess.run(["gh", "release", "view", tag, "--repo", GITHUB_REPO], capture_output=True, text=True, encoding="utf-8", errors="replace")
        tag_exists = (gh_check.returncode == 0)
        
        if tag_exists:
            print(f"      WARNING: GitHub release {tag} already exists. Appending release assets instead...")
            run_gh_cmd(["gh", "release", "upload", tag, str(zip_path), "--clobber", "--repo", GITHUB_REPO])
        else:
            # Create release
            run_gh_cmd(["gh", "release", "create", tag, str(zip_path), "--title", title, "--notes", notes, "--repo", GITHUB_REPO, "--target", "main"])
        print(f"\nBuild and packaging complete! Packaged zip file is ready at: dist/{zip_path.name}")
    else:
        print("      GitHub CLI ('gh') was not found in PATH.")
        print("      To complete publication:")
        print(f"      1. Go to your GitHub repository.")
        print(f"      2. Create a new Release with tag 'v{APP_VERSION}'.")
        print(f"      3. Drag-and-drop the distribution zip file into the release assets:")
        print(f"         📁 {zip_path}")
        print("\nBuild and packaging complete! Ready for manual upload.")

if __name__ == "__main__":
    main()
