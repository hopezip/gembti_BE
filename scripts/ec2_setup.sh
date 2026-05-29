#!/bin/bash
# EC2 초기 세팅 스크립트 (Ubuntu 24.04 LTS)
# 사용법: ssh 접속 후 bash ec2_setup.sh

set -e

echo "=== 1. 시스템 패키지 업데이트 ==="
sudo apt-get update -y && sudo apt-get upgrade -y

echo "=== 2. Docker 설치 ==="
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# 현재 유저를 docker 그룹에 추가 (재로그인 필요)
sudo usermod -aG docker $USER

echo "=== 3. Docker 서비스 시작 ==="
sudo systemctl enable docker
sudo systemctl start docker

echo "=== 4. Docker 네트워크 생성 ==="
docker network create gembti_net || true

echo "=== 5. 볼륨 생성 ==="
docker volume create postgres_data || true
docker volume create redis_data   || true

echo "=== 6. 앱 디렉터리 생성 ==="
mkdir -p ~/gembti

echo ""
echo "✅ 완료!"
echo ""
echo "▶ 다음 단계:"
echo "  1. ~/gembti/.env 파일을 .env.example 기반으로 생성하세요"
echo "  2. 환경변수 중 DB/Redis 호스트를 컨테이너 이름으로 설정하세요:"
echo "     DATABASE_URL=postgresql+asyncpg://gembti:pw@gembti_postgres:5432/gembti"
echo "     REDIS_URL=redis://gembti_redis:6379/0"
echo "  3. 재로그인 후 docker 명령어를 sudo 없이 사용할 수 있습니다"
