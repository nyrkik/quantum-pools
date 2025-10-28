#!/bin/bash
# Project Health Check - Runs automatically via git pre-commit hook

echo "=== PROJECT HEALTH CHECK ==="
echo

# 1. Source code file count (should stay under 500)
SOURCE_FILES=$(find app/ docs/ scripts/ -type f \( -name "*.py" -o -name "*.js" -o -name "*.md" \) 2>/dev/null | wc -l)
echo "Source files: $SOURCE_FILES / 500"
if [ "$SOURCE_FILES" -gt 500 ]; then
    echo "⚠️  WARNING: Source code exceeds 500 files. Consider refactoring."
fi

# 2. Python file size check (no file should exceed 500 lines)
echo
LARGE_PY=$(find app/ -name "*.py" -exec wc -l {} \; 2>/dev/null | awk '$1 > 500 {print $1 " lines: " $2}')
if [ -n "$LARGE_PY" ]; then
    echo "⚠️  Python files exceeding 500 lines:"
    echo "$LARGE_PY"
fi

# 3. Documentation size check (no doc should exceed 500 lines)
echo
LARGE_DOCS=$(find docs/ -name "*.md" -exec wc -l {} \; 2>/dev/null | awk '$1 > 500 {print $1 " lines: " $2}')
if [ -n "$LARGE_DOCS" ]; then
    echo "⚠️  Docs exceeding 500 lines:"
    echo "$LARGE_DOCS"
fi

# 4. Venv size check (should stay under 600MB)
VENV_SIZE=$(du -sm venv/ 2>/dev/null | cut -f1)
echo
echo "Venv size: ${VENV_SIZE}MB / 600MB"
if [ "$VENV_SIZE" -gt 600 ]; then
    echo "⚠️  WARNING: Venv exceeds 600MB. Check for bloat."
    echo "Largest packages:"
    du -sm venv/lib/python*/site-packages/* 2>/dev/null | sort -rn | head -5
fi

# 5. Git repo size check (should stay under 100MB)
GIT_SIZE=$(du -sm .git/ 2>/dev/null | cut -f1)
echo
echo "Git repo size: ${GIT_SIZE}MB / 100MB"
if [ "$GIT_SIZE" -gt 100 ]; then
    echo "⚠️  WARNING: Git repo exceeds 100MB. May have large files in history."
fi

# 6. Check for files that shouldn't be tracked
echo
SHOULD_NOT_EXIST=""
[ -f "SESSION_LOG.md" ] && SHOULD_NOT_EXIST="${SHOULD_NOT_EXIST}❌ SESSION_LOG.md exists (should be deleted)\n"
[ -d "node_modules" ] && SHOULD_NOT_EXIST="${SHOULD_NOT_EXIST}❌ node_modules/ exists (wrong framework?)\n"
[ -f ".env" ] && git ls-files --error-unmatch .env 2>/dev/null && SHOULD_NOT_EXIST="${SHOULD_NOT_EXIST}❌ .env is tracked by git (security risk)\n"

if [ -n "$SHOULD_NOT_EXIST" ]; then
    echo "Files that shouldn't exist:"
    echo -e "$SHOULD_NOT_EXIST"
fi

# 7. Dependency count check
echo
REQUIREMENTS_COUNT=$(grep -c "==" requirements.txt 2>/dev/null || echo 0)
echo "Direct dependencies: $REQUIREMENTS_COUNT / 25"
if [ "$REQUIREMENTS_COUNT" -gt 25 ]; then
    echo "⚠️  WARNING: >25 dependencies. Consider if all are needed."
fi

echo
echo "=== END HEALTH CHECK ==="
