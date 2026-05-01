### Development Guide

#### 1. Build/Configuration Instructions

**Project Setup:**
1. **Prerequisites**: Python 3.10+, Docker Desktop, GitHub CLI (gh).
2. **Environment**:
   - Create a virtual environment: python -m venv .venv`n   - Activate: .venv\Scripts\activate (Windows) or source .venv/bin/activate (Mac/Linux).
   - Install dependencies: pip install -r requirements.txt`n3. **Internal CLI**:
   - Install the skuld CLI: cd ops/skuld-cli && pip install -e . && cd ../..`n   - Verify setup: skuld doctor`n4. **Database**:
   - Use .\setup_scripts\manage_local_db.ps1 to start a local PostgreSQL DB.
   - For remote access, an SSH tunnel is required (configured in .env via SSH_PKEY_PATH, SSH_HOST, SSH_USER).
5. **Running the App**:
   - streamlit run Skuld/app.py (accessible at http://localhost:8501).

#### 2. Testing Information

**Configuring and Running Tests:**
- The project uses pytest.
- Run all tests: pytest`n- Run a specific test file: pytest tests/test_name.py`n
**Adding New Tests:**
- Place new test files in the 	ests/ directory with the prefix 	est_.
- Use pytest.fixture for reusable data (see 	ests/test_spreads_calculation.py for examples with Pandas DataFrames).

**Example Test:**
Create a file 	ests/test_simple_example.py:
`python
def test_addition():
    assert 1 + 1 == 2
` 
Run it: pytest tests/test_simple_example.py`n
#### 3. Additional Development Information

- **Language Policy**: 
  - **All code, documentation, tests, and comments must always be written in English.**
- **Code Style & Logging**: 
  - Use the @log_function decorator from src.decorator_log_function for automatic logging of function entry, parameters, execution time, and results (especially useful for DataFrames).
  - Use the logger from logging.getLogger(__name__) for standard logging.
- **Database Access**: 
  - Use src.database.get_postgres_engine() to get a SQLAlchemy engine. It implements a Singleton pattern and handles SSH tunneling automatically.
- **Configuration**: 
  - Central configuration is in config.py, which loads from .env.
- **Architecture**: 
  - Streamlit frontend, PostgreSQL backend.
  - Deployment is managed via GitHub Actions and the skuld CLI.
  - Production deployments happen automatically on push to master.
