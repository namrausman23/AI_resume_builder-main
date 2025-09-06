import subprocess
import sys
import os


def run(cmd):
    print(f"\n🔧 Running: {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {e.cmd}")
        sys.exit(1)


# Step 1: Create virtual environment
venv_dir = "venv"
print(f"\n📁 Creating virtual environment at ./{venv_dir} ...")
subprocess.run([sys.executable, "-m", "venv", venv_dir])

# Determine pip path based on OS
pip_path = os.path.join(venv_dir, "Scripts", "pip.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "pip")

# Step 2: Install Python dependencies
print("\n📥 Installing Python dependencies...")

packages = [
    "flask",
    "flask-cors",
    "python-dotenv",
    "Werkzeug",
    "google-generativeai",
    "docx2txt",
    "pymupdf",      # aka fitz
    "jinja2",
    "pdflatex"
]

run(f"{pip_path} install " + " ".join(packages))

# Step 3: Create .env file if not exists
env_path = ".env"
if not os.path.exists(env_path):
    print("\n🛠️ Creating .env file...")
    with open(env_path, "w") as f:
        f.write("GEMINI_API_KEY=your_google_api_key_here\n")
    print("⚠️  Don't forget to replace 'your_google_api_key_here' with your actual API key!")
else:
    print("\n✅ .env file already exists.")

# Step 4: Done
print("\n✅ All set!")
if os.name == "nt":
    print("🔧 To activate: venv\\Scripts\\activate")
else:
    print("🔧 To activate: source venv/bin/activate")
