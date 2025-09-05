import os

def check_env_vars():
    """
    Checks if all environment variables from env.sample are present in .env.
    """
    try:
        with open('env.sample', 'r', encoding='utf-8') as f:
            sample_vars = {line.split('=')[0].strip() for line in f if '=' in line and not line.strip().startswith('#')}

        if not os.path.exists('.env'):
            print("'.env' file not found. All required variables are missing:")
            for var in sorted(sample_vars):
                print(f"- {var}")
            return

        with open('.env', 'r', encoding='utf-8') as f:
            env_vars = {line.split('=')[0].strip() for line in f if '=' in line and not line.strip().startswith('#')}

        missing_vars = sample_vars - env_vars

        if not missing_vars:
            print("✅ All required environment variables are present in '.env'.")
        else:
            print("⚠️ Missing environment variables in '.env':")
            for var in sorted(missing_vars):
                print(f"- {var}")

    except FileNotFoundError as e:
        print(f"Error: {e}. Make sure 'env.sample' is in the root directory.")

if __name__ == "__main__":
    check_env_vars()
