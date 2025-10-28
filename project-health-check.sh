#!/bin/bash
# Project Health Check - Runs automatically via git pre-commit hook

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PROJECT HEALTH CHECK ===${NC}"
echo

# 1. Source code file count (should stay under 500)
SOURCE_FILES=$(find app/ docs/ scripts/ -type f \( -name "*.py" -o -name "*.js" -o -name "*.md" \) 2>/dev/null | wc -l)
if [ "$SOURCE_FILES" -gt 500 ]; then
    echo -e "${RED}Source files: $SOURCE_FILES / 500${NC}"
    echo -e "${RED}⚠️  WARNING: Source code exceeds 500 files. Consider refactoring.${NC}"
elif [ "$SOURCE_FILES" -gt 400 ]; then
    echo -e "${YELLOW}Source files: $SOURCE_FILES / 500${NC}"
else
    echo -e "${GREEN}Source files: $SOURCE_FILES / 500${NC}"
fi

# 2. Python file size check (no file should exceed 500 lines) - ONLY in app/
echo
LARGE_PY=$(find app/ -name "*.py" ! -path "*/venv/*" -exec wc -l {} \; 2>/dev/null | awk '$1 > 500 {print $1 " lines: " $2}')
if [ -n "$LARGE_PY" ]; then
    echo -e "${YELLOW}⚠️  Python files exceeding 500 lines:${NC}"
    echo "$LARGE_PY"
fi

# 3. Documentation size check (no doc should exceed 500 lines)
echo
LARGE_DOCS=$(find docs/ -name "*.md" -exec wc -l {} \; 2>/dev/null | awk '$1 > 500 {print $1 " lines: " $2}')
if [ -n "$LARGE_DOCS" ]; then
    echo -e "${YELLOW}⚠️  Docs exceeding 500 lines:${NC}"
    echo "$LARGE_DOCS"
fi

# 4. Venv size check (should stay under 600MB) - at root level
VENV_SIZE=$(du -sm venv/ 2>/dev/null | cut -f1)
echo
if [ "$VENV_SIZE" -gt 600 ]; then
    echo -e "${RED}Venv size: ${VENV_SIZE}MB / 600MB${NC}"
    echo -e "${RED}⚠️  WARNING: Venv exceeds 600MB. Check for bloat.${NC}"
    echo "Largest packages:"
    du -sm venv/lib/python*/site-packages/* 2>/dev/null | sort -rn | head -5
elif [ "$VENV_SIZE" -gt 500 ]; then
    echo -e "${YELLOW}Venv size: ${VENV_SIZE}MB / 600MB${NC}"
else
    echo -e "${GREEN}Venv size: ${VENV_SIZE}MB / 600MB${NC}"
fi

# 5. Git repo size check (should stay under 100MB)
GIT_SIZE=$(du -sm .git/ 2>/dev/null | cut -f1)
echo
if [ "$GIT_SIZE" -gt 100 ]; then
    echo -e "${RED}Git repo size: ${GIT_SIZE}MB / 100MB${NC}"
    echo -e "${RED}⚠️  WARNING: Git repo exceeds 100MB. May have large files in history.${NC}"
elif [ "$GIT_SIZE" -gt 75 ]; then
    echo -e "${YELLOW}Git repo size: ${GIT_SIZE}MB / 100MB${NC}"
else
    echo -e "${GREEN}Git repo size: ${GIT_SIZE}MB / 100MB${NC}"
fi

# 6. Check for files that shouldn't be tracked
echo
SHOULD_NOT_EXIST=""
[ -f "SESSION_LOG.md" ] && SHOULD_NOT_EXIST="${SHOULD_NOT_EXIST}${RED}❌ SESSION_LOG.md exists (should be deleted)${NC}\n"
[ -d "node_modules" ] && SHOULD_NOT_EXIST="${SHOULD_NOT_EXIST}${RED}❌ node_modules/ exists (wrong framework?)${NC}\n"
[ -f ".env" ] && git ls-files --error-unmatch .env 2>/dev/null && SHOULD_NOT_EXIST="${SHOULD_NOT_EXIST}${RED}❌ .env is tracked by git (security risk)${NC}\n"

if [ -n "$SHOULD_NOT_EXIST" ]; then
    echo "Files that shouldn't exist:"
    echo -e "$SHOULD_NOT_EXIST"
fi

# 7. Dependency count check
echo
REQUIREMENTS_COUNT=$(grep -c "==" requirements.txt 2>/dev/null || echo 0)
if [ "$REQUIREMENTS_COUNT" -gt 25 ]; then
    echo -e "${RED}Direct dependencies: $REQUIREMENTS_COUNT / 25${NC}"
    echo -e "${RED}⚠️  WARNING: >25 dependencies. Consider if all are needed.${NC}"
elif [ "$REQUIREMENTS_COUNT" -gt 20 ]; then
    echo -e "${YELLOW}Direct dependencies: $REQUIREMENTS_COUNT / 25${NC}"
else
    echo -e "${GREEN}Direct dependencies: $REQUIREMENTS_COUNT / 25${NC}"
fi

echo
echo -e "${GREEN}=== END HEALTH CHECK ===${NC}"
