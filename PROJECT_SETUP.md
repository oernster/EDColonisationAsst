# Elite: Dangerous Colonisation Assistant - Project Setup Guide

## Quick Start

This guide will help you set up the development environment and understand the project structure.

## Prerequisites

### Backend Requirements
- Python 3.10 or higher
- pip (Python package manager)
- Virtual environment support

### Frontend Requirements
- Node.js 18+ and npm (or yarn/pnpm)
- Modern web browser

### System Requirements
- Windows (for Elite: Dangerous journal file access)
- Elite: Dangerous installed with journal files at:
  `C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous`

## Project Structure

```
EDColonisationAsst/
├── ARCHITECTURE.md           # Detailed architecture documentation
├── PROJECT_SETUP.md         # This file
├── README.md                # Project overview
├── .gitignore              # Git ignore rules
├── backend/                # Python backend
│   ├── src/               # Source code
│   ├── tests/             # Test files
│   ├── requirements.txt   # Production dependencies
│   ├── requirements-dev.txt  # Development dependencies
│   ├── pytest.ini         # Pytest configuration
│   ├── mypy.ini          # Type checking configuration
│   └── README.md         # Backend-specific docs
├── frontend/              # React frontend
│   ├── src/              # Source code
│   ├── public/           # Static assets
│   ├── tests/            # Test files
│   ├── package.json      # Node dependencies
│   ├── tsconfig.json     # TypeScript configuration
│   ├── vite.config.ts    # Vite build configuration
│   └── README.md         # Frontend-specific docs
└── docs/                 # Additional documentation
    ├── API.md           # API documentation
    ├── TESTING.md       # Testing guide
    └── DEPLOYMENT.md    # Deployment guide
```

## Step-by-Step Setup

### 1. Clone/Initialize Repository

```bash
# If starting fresh
mkdir EDColonisationAsst
cd EDColonisationAsst
git init
```

### 2. Backend Setup

```bash
# Create backend directory structure
mkdir -p backend/src/models
mkdir -p backend/src/services
mkdir -p backend/src/repositories
mkdir -p backend/src/api
mkdir -p backend/src/utils
mkdir -p backend/tests/unit
mkdir -p backend/tests/integration
mkdir -p backend/tests/fixtures

# Create virtual environment
cd backend
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Create requirements.txt
cat > requirements.txt << EOF
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
watchdog==3.0.0
websockets==12.0
python-multipart==0.0.6
aiofiles==23.2.1
EOF

# Create requirements-dev.txt
cat > requirements-dev.txt << EOF
-r requirements.txt
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-mock==3.12.0
mypy==1.7.1
black==23.11.0
isort==5.12.0
pylint==3.0.3
httpx==0.25.2
EOF

# Install dependencies
pip install -r requirements-dev.txt
```

### 3. Frontend Setup

```bash
# Create frontend with Vite
cd ..
npm create vite@latest frontend -- --template react-ts

cd frontend

# Install additional dependencies
npm install @mui/material @emotion/react @emotion/styled
npm install zustand axios
npm install -D @testing-library/react @testing-library/jest-dom
npm install -D @types/node

# Install development dependencies
npm install -D vitest @vitest/ui jsdom
```

### 4. Configuration Files

#### Backend Configuration

Create `backend/config.yaml`:
```yaml
journal:
  directory: "C:\\Users\\%USERNAME%\\Saved Games\\Frontier Developments\\Elite Dangerous"
  watch_interval: 1.0

server:
  host: "0.0.0.0"
  port: 8000
  cors_origins:
    - "http://localhost:5173"

  # websocket: (legacy / unused)
  # Live updates are implemented using AJAX long-polling at /api/changes/longpoll.
  # websocket:
  #   ping_interval: 30
  #   reconnect_attempts: 5

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

Create `backend/.env`:
```bash
ED_JOURNAL_PATH=C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous
API_HOST=localhost
API_PORT=8000
LOG_LEVEL=INFO
```

Create `backend/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --cov=src
    --cov-report=html
    --cov-report=term-missing
asyncio_mode = auto
```

Create `backend/mypy.ini`:
```ini
[mypy]
python_version = 3.10
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
disallow_incomplete_defs = True
check_untyped_defs = True
no_implicit_optional = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_no_return = True
strict_equality = True

[mypy-tests.*]
disallow_untyped_defs = False
```

#### Frontend Configuration

Update `frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

### 5. Git Configuration

Create `.gitignore`:
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/

# Node
node_modules/
dist/
.cache/
*.log
npm-debug.log*

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Environment
.env
.env.local
config.local.yaml

# Test coverage
coverage/
.nyc_output/
```

## Development Workflow

### Backend Development

```bash
# Activate virtual environment
cd backend
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Type checking
mypy src/

# Format code
black src/ tests/
isort src/ tests/

# Lint
pylint src/

# Run development server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development

```bash
cd frontend

# Run tests
npm test

# Run tests in watch mode
npm run test:watch

# Type checking
npm run type-check

# Development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Testing Strategy

### Backend Testing

1. **Unit Tests**: Test individual components in isolation
   ```bash
   pytest tests/unit/ -v
   ```

2. **Integration Tests**: Test component interactions
   ```bash
   pytest tests/integration/ -v
   ```

3. **Coverage Report**:
   ```bash
   pytest --cov=src --cov-report=html
   # Open htmlcov/index.html in browser
   ```

### Frontend Testing

1. **Component Tests**:
   ```bash
   npm test -- --run
   ```

2. **Watch Mode**:
   ```bash
   npm test
   ```

3. **Coverage**:
   ```bash
   npm test -- --coverage
   ```

## Running the Application

### Development Mode

1. **Start Backend**:
   ```bash
   cd backend
   venv\Scripts\activate
   uvicorn src.main:app --reload
   ```
   Backend will be available at: http://localhost:8000
   API docs at: http://localhost:8000/docs

2. **Start Frontend** (in new terminal):
   ```bash
   cd frontend
   npm run dev
   ```
   Frontend will be available at: http://localhost:5173

3. **Ensure Elite: Dangerous is running** or has recent journal files

### Production Mode

1. **Build Frontend**:
   ```bash
   cd frontend
   npm run build
   ```

2. **Run Backend with Production Settings**:
   ```bash
   cd backend
   venv\Scripts\activate
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

## Troubleshooting

### Backend Issues

**Problem**: Cannot find journal files
- **Solution**: Check the path in `config.yaml` matches your Elite: Dangerous installation
- Verify: `C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous`

**Problem**: Import errors
- **Solution**: Ensure virtual environment is activated and dependencies installed
  ```bash
  pip install -r requirements.txt
  ```

**Problem**: Tests failing
- **Solution**: Check Python version (3.10+) and run:
  ```bash
  pip install -r requirements-dev.txt
  pytest -v
  ```

### Frontend Issues

**Problem**: Cannot connect to backend
- **Solution**: Ensure backend is running on port 8000
- Check proxy configuration in `vite.config.ts`

**Problem**: Live updates not working
- **Solution**: Verify the long-poll endpoint is reachable:
  - `GET /api/changes/longpoll?since=0&timeout_s=1`
  - Trigger a journal change and confirm it returns `changed: true`.
- Check CORS settings in backend.

**Problem**: Build errors
- **Solution**: Clear node_modules and reinstall:
  ```bash
  rm -rf node_modules package-lock.json
  npm install
  ```

## Next Steps

1. **Review Architecture**: Read `ARCHITECTURE.md` for detailed design
2. **Start with Tests**: Begin with test-driven development
3. **Implement Backend**: Start with journal parser and data models
4. **Implement Frontend**: Build UI components incrementally
5. **Integration**: Connect frontend to backend via REST + AJAX long-poll (`/api/changes/longpoll`)
6. **Testing**: Comprehensive testing at each stage
7. **Documentation**: Keep docs updated as you build

## Useful Commands Reference

### Backend
```bash
# Run specific test file
pytest tests/unit/test_journal_parser.py -v

# Run tests matching pattern
pytest -k "test_parse" -v

# Run with debugging
pytest --pdb

# Generate coverage report
pytest --cov=src --cov-report=term-missing

# Format and lint
black src/ && isort src/ && pylint src/
```

### Frontend
```bash
# Run specific test file
npm test -- src/components/SystemSelector.test.tsx

# Update snapshots
npm test -- -u

# Run tests with UI
npm run test:ui

# Build and analyze bundle
npm run build -- --mode production
```

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Material-UI Documentation](https://mui.com/)
- [Elite: Dangerous Journal Documentation](https://elite-journal.readthedocs.io/)

## Support

For issues or questions:
1. Check `ARCHITECTURE.md` for design decisions
2. Review test files for usage examples
3. Check API documentation at `/docs` endpoint
4. Review Elite: Dangerous journal file format

---

Happy coding! 🚀
