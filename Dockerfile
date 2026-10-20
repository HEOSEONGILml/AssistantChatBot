# 웹 프로토타입 컨테이너 (0017): 웹 화면을 빌드하고 두뇌 웹 모드가 페이지·토큰·WebSocket을 한 포트로 낸다
FROM node:22-slim AS web
WORKDIR /src/app
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build:web

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /src/brain
COPY brain/pyproject.toml brain/uv.lock ./
RUN uv sync --frozen --no-dev
COPY brain/ ./
COPY --from=web /src/app/dist-web /src/app/dist-web
# 데이터 폴더는 $APPDATA/TamagotchiChatBot/brain/web (config.web_data_dir). 강아지는 저장하지 않고 로그만 볼륨에 남는다 (0021)
ENV APPDATA=/data PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8787
CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "brain.web", "--host", "0.0.0.0", "--port", "8787"]
