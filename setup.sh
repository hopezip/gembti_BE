set -e

echo "📁 폴더 및 빈 파일 생성 중..."

# 폴더 생성
mkdir -p app/core
mkdir -p app/common
mkdir -p app/chat_common
mkdir -p app/auth
mkdir -p app/steam
mkdir -p app/survey
mkdir -p app/stat
mkdir -p app/recommend
mkdir -p app/game
mkdir -p app/chat
mkdir -p app/support
mkdir -p alembic/versions
mkdir -p tests
mkdir -p nginx/conf.d
mkdir -p scripts
mkdir -p docs/help/support
mkdir -p .github/workflows

# __init__.py
touch app/__init__.py
touch app/core/__init__.py
touch app/common/__init__.py
touch app/chat_common/__init__.py
touch app/auth/__init__.py
touch app/steam/__init__.py
touch app/survey/__init__.py
touch app/stat/__init__.py
touch app/recommend/__init__.py
touch app/game/__init__.py
touch app/chat/__init__.py
touch app/support/__init__.py
touch tests/__init__.py

# main.py
touch app/main.py

# core/
touch app/core/config.py
touch app/core/database.py
touch app/core/redis.py
touch app/core/celery_app.py
touch app/core/security.py
touch app/core/dependencies.py
touch app/core/exceptions.py
touch app/core/middlewares.py