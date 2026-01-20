import time
import subprocess
from datetime import datetime

def run_command(command):
    """Running shell command and print output"""
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        if result.stdout:
            print(result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running '{command}':")
        print(e.stderr.strip())
        return False

def main():
    print("🚀 Starting Auto Git Sync (Add -> Commit -> Push) every 60s")
    print("Press Ctrl+C to stop.")
    
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] ----------------------------------------")
        
        # 1. Git Add
        print("📝 Executing: git add .")
        run_command("git add .")
        
        # Check if there are changes to commit
        status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
        
        if status.stdout.strip():
            # 2. Git Commit
            commit_msg = f"Auto save {timestamp}"
            print(f"💾 Executing: git commit -m '{commit_msg}'")
            if run_command(f'git commit -m "{commit_msg}"'):
                # 3. Git Push (only push if commit was successful)
                print("⬆️  Executing: git push")
                run_command("git push")
        else:
            print("ℹ️  No changes to commit.")
            # Optional: Push anyway to sync previous commits
            # print("⬆️  Executing: git push (sync check)")
            # run_command("git push")
            
        print("⏳ Waiting 60 seconds...")
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
            break

if __name__ == "__main__":
    main()
