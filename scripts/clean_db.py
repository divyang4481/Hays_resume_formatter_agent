import os
import sys
import re
from pathlib import Path

def load_env_file():
    # Try to load .env from current directory or project root
    env_paths = [Path(".env"), Path(__file__).resolve().parents[1] / ".env"]
    for path in env_paths:
        if path.is_file():
            print(f"Loading environment from {path.resolve()}")
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        # Strip quotes if present
                        v = v.strip().strip("'\"")
                        os.environ[k.strip()] = v
            break

def main():
    load_env_file()
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[Error] DATABASE_URL not found in environment or .env file.")
        sys.exit(1)
        
    # Mask password for display
    display_url = db_url
    if "@" in db_url:
        parts = db_url.split("@", 1)
        prefix = parts[0]
        suffix = parts[1]
        if ":" in prefix:
            proto_user, _ = prefix.rsplit(":", 1)
            display_url = f"{proto_user}:***@{suffix}"
        else:
            display_url = f"***@{suffix}"
            
    print(f"Database URL: {display_url}")
    
    # Standardize URL for psycopg (remove any +psycopg / +psycopg2 suffix from protocol)
    if db_url.startswith("postgresql+"):
        db_url = re.sub(r"^postgresql\+[a-zA-Z0-9_-]+://", "postgresql://", db_url)
    
    try:
        import psycopg
    except ImportError:
        print("[Error] psycopg (v3) is not installed. Please run: pip install psycopg[binary]")
        sys.exit(1)
        
    print("Connecting to database...")
    try:
        with psycopg.connect(db_url) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Fetch all tables in the public schema
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
                tables = [row[0] for row in cur.fetchall()]
                
                if not tables:
                    print("No tables found to clean.")
                    return
                
                print(f"Found {len(tables)} tables: {', '.join(tables)}")
                for table in tables:
                    print(f"Truncating table: {table}...")
                    cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
                
                print("Database cleaned successfully!")
    except Exception as e:
        print(f"[Error] Failed to clean database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
