import os
import psycopg2

def load_env_file():
    """Reads the .env configuration file explicitly using only the Python standard library."""
    # Find the root folder path where the .env file lives
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, '.env')
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                # Clean up lines and ignore comments or empty entries
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                # Save the parameter configuration straight to your environment system
                os.environ[key.strip()] = val.strip()

def init_postgresql_schema():
    # Load the environment details before starting the database connection engine
    load_env_file()
    
    try:
        print("Connecting to your local PostgreSQL Cluster...")
        conn = psycopg2.connect(
            dbname=os.environ.get('SENTINEL_DB_NAME', 'sentinel_police'),
            user=os.environ.get('SENTINEL_DB_USER', 'postgres'),
            password=os.environ.get('SENTINEL_DB_PASSWORD', ''),
            host=os.environ.get('SENTINEL_DB_HOST', '127.0.0.1'),
            port=os.environ.get('SENTINEL_DB_PORT', '5432')
        )
        cur = conn.cursor()
        
        # 1. Central Persons Registry Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id SERIAL PRIMARY KEY,
            person_id VARCHAR(50) UNIQUE NOT NULL,
            first_name VARCHAR(100) NOT NULL,
            second_name VARCHAR(100) NOT NULL,
            third_name VARCHAR(100) NOT NULL,
            fourth_name VARCHAR(100) NOT NULL,
            mother_name VARCHAR(255),
            dob DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 2. Police Officers Core HR Roster Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS officers (
            id SERIAL PRIMARY KEY,
            service_id VARCHAR(50) UNIQUE NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            rank VARCHAR(100) NOT NULL,
            assigned_station VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 3. Officer Immutable Service History Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS officer_service_history (
            id SERIAL PRIMARY KEY,
            officer_id VARCHAR(50) REFERENCES officers(service_id) ON DELETE CASCADE,
            action_type VARCHAR(100) NOT NULL,
            narrative TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("SUCCESS: Relational database structures created successfully inside pgAdmin!")
        
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\nDATABASE CONNECTION ERROR: {error}")
        print("Please double-check your SENTINEL_DB_PASSWORD inside your .env file.")

if __name__ == '__main__':
    init_postgresql_schema()
