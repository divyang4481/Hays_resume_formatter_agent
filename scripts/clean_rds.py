import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Path to CloudFormation parameters file (relative to project root)
PARAMS_FILE = (
    Path(__file__).resolve().parents[2]
    / "Hays_resume_formatter_agent"
    / "infra"
    / "cloudformation"
    / "parameters-hay-agent-example.json"
)


def load_params():
    if not PARAMS_FILE.is_file():
        print(f"[Error] Parameters file not found: {PARAMS_FILE}")
        sys.exit(1)
    with open(PARAMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def confirm(prompt: str) -> bool:
    resp = input(f"{prompt} (yes/[no]): ").strip().lower()
    return resp == "yes"


def run_aws(command: list[str]):
    try:
        result = subprocess.run(
            ["aws"] + command, check=True, capture_output=True, text=True
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"[AWS Error] {e.stderr}")
        sys.exit(1)


def delete_stack(stack_name: str, yes: bool):
    if not yes and not confirm(
        f"Are you sure you want to DELETE CloudFormation stack '{stack_name}'?"
    ):
        print("Aborted.")
        return
    print(f"Deleting CloudFormation stack '{stack_name}'…")
    run_aws(["cloudformation", "delete-stack", "--stack-name", stack_name])
    print(
        "Delete request sent. Use 'aws cloudformation describe-stacks' to monitor progress."
    )


def create_stack(
    stack_name: str, template_path: Path, parameters_path: Path, yes: bool
):
    if not yes and not confirm(
        f"Create new stack '{stack_name}' with template {template_path}?"
    ):
        print("Aborted.")
        return
    print(f"Creating CloudFormation stack '{stack_name}'…")
    run_aws(
        [
            "cloudformation",
            "create-stack",
            "--stack-name",
            stack_name,
            "--template-body",
            f"file://{template_path}",
            "--parameters",
            f"file://{parameters_path}",
            "--capabilities",
            "CAPABILITY_NAMED_IAM",
        ]
    )
    print(
        "Create request sent. Use 'aws cloudformation describe-stacks' to monitor progress."
    )


def truncate_tables(
    db_host: str, db_name: str, db_user: str, db_pass: str, engine: str = "postgresql"
):
    if engine == "postgresql":
        try:
            import psycopg2  # type: ignore
        except ImportError:
            print("[Error] psycopg2 not installed. Install it or use another engine.")
            sys.exit(1)
        conn = psycopg2.connect(
            host=db_host, dbname=db_name, user=db_user, password=db_pass
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
        tables = [row[0] for row in cur.fetchall()]
        for tbl in tables:
            print(f"Truncating table {tbl}…")
            cur.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")
        cur.close()
        conn.close()
        print("All tables truncated.")
    else:
        print(f"[Error] Engine '{engine}' not supported for automatic truncate.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Utility to clean the RDS instance used by the Hays resume agent."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["full-recreate", "truncate-tables", "delete-stack"],
        help="Cleaning mode.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts.")
    args = parser.parse_args()

    params = load_params()

    # Extract values we need – parameter dicts have keys ParameterKey/ParameterValue
    def get_param(key):
        for p in params:
            if p.get("ParameterKey") == key:
                return p.get("ParameterValue")
        return None

    stack_name = f"{get_param('ProjectName')}-{get_param('Environment')}-stack"
    template_path = (
        Path(__file__).resolve().parents[2]
        / "infra"
        / "cloudformation"
        / "template.yaml"
    )

    if args.mode == "full-recreate":
        # Delete then create the stack
        delete_stack(stack_name, args.yes)
        # Note: creation may need to wait until deletion finishes; user should re‑run when ready.
        create_stack(stack_name, template_path, PARAMS_FILE, args.yes)
    elif args.mode == "delete-stack":
        delete_stack(stack_name, args.yes)
    elif args.mode == "truncate-tables":
        # Basic DB connection info – you may need to add DBHost to parameters file.
        db_host = os.getenv("DB_HOST") or get_param("DBEndpoint") or "localhost"
        db_name = get_param("DBName")
        db_user = get_param("DBUsername")
        db_pass = get_param("DBPassword")
        if not all([db_name, db_user, db_pass]):
            print(
                "[Error] Missing DB credentials in parameters file or environment variables."
            )
            sys.exit(1)
        truncate_tables(db_host, db_name, db_user, db_pass)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
